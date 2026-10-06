import json
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.modules.setdefault("pyodbc", types.ModuleType("pyodbc"))

from inventory_backend_client import (
    InventoryBackendClientError,
    PackageApiResponse,
    _multipart_zip_body,
)
from package_upload_store import PackageUploadRecord, PackageUploadStore
from session_package_export import SessionPackageExportContext
from session_package_upload import (
    PackageUploadError,
    ensure_session_package_exported,
    upload_session_package,
)
from inventory_context_fixture import install_test_inventory_context
from test_session_package_export import build_finished_session
from package_upload_store import PackageUploadRecord


class RecordingBackendClient:
    def __init__(
        self,
        *,
        preview: PackageApiResponse | None = None,
        confirm: PackageApiResponse | None = None,
        preview_error: InventoryBackendClientError | None = None,
        confirm_error: InventoryBackendClientError | None = None,
    ) -> None:
        self.preview_calls: list[dict[str, object]] = []
        self.confirm_calls: list[dict[str, object]] = []
        self._preview = preview
        self._confirm = confirm
        self._preview_error = preview_error
        self._confirm_error = confirm_error

    def preview_local_inventory_package(
        self,
        *,
        inventory_id: str,
        zip_bytes: bytes,
        file_name: str,
    ) -> PackageApiResponse:
        self.preview_calls.append(
            {
                "inventory_id": inventory_id,
                "zip_bytes": zip_bytes,
                "file_name": file_name,
            }
        )
        if self._preview_error is not None:
            raise self._preview_error
        assert self._preview is not None
        return self._preview

    def confirm_local_inventory_package(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str = "SKIP",
    ) -> PackageApiResponse:
        self.confirm_calls.append(
            {
                "inventory_id": inventory_id,
                "export_id": export_id,
                "conflict_policy": conflict_policy,
            }
        )
        if self._confirm_error is not None:
            raise self._confirm_error
        assert self._confirm is not None
        return self._confirm


def _preview_response(
    *,
    export_id: str,
    inventory_id: str = "inventory-1",
    package_id: str = "pkg-1",
) -> PackageApiResponse:
    return PackageApiResponse(
        raw={
            "export_id": export_id,
            "package_id": package_id,
            "inventory_id": inventory_id,
            "status": "PREVIEWED",
            "duplicate": False,
        },
        package_id=package_id,
        export_id=export_id,
        inventory_id=inventory_id,
        status="PREVIEWED",
        duplicate=False,
    )


def _confirm_response(
    *,
    export_id: str,
    inventory_id: str = "inventory-1",
    package_id: str = "pkg-1",
    duplicate: bool = False,
) -> PackageApiResponse:
    return PackageApiResponse(
        raw={
            "export_id": export_id,
            "package_id": package_id,
            "inventory_id": inventory_id,
            "status": "CONFIRMED",
            "duplicate": duplicate,
        },
        package_id=package_id,
        export_id=export_id,
        inventory_id=inventory_id,
        status="CONFIRMED",
        duplicate=duplicate,
    )


class SessionPackageUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        install_test_inventory_context(self.root)
        self.out = self.root / "packages"
        self.upload_store = PackageUploadStore(self.root / "upload-state")
        self.context = SessionPackageExportContext(
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            device_id="device-rpi-1",
        )

    def _export_session(self) -> tuple[str, str, Path]:
        _, store, photos_root, session_id = build_finished_session(self.root)
        outcome = ensure_session_package_exported(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
            upload_store=self.upload_store,
        )
        return session_id, outcome.export_id, outcome.zip_path

    def test_valid_zip_sends_correct_preview_request(self) -> None:
        session_id, export_id, zip_path = self._export_session()
        zip_bytes = zip_path.read_bytes()
        client = RecordingBackendClient(
            preview=_preview_response(export_id=export_id),
            confirm=_confirm_response(export_id=export_id),
        )
        upload_session_package(
            capture_session_id=session_id,
            inventory_id=self.context.inventory_id,
            upload_store=self.upload_store,
            backend_client=client,
        )
        self.assertEqual(len(client.preview_calls), 1)
        call = client.preview_calls[0]
        self.assertEqual(call["inventory_id"], "inventory-1")
        self.assertEqual(call["zip_bytes"], zip_bytes)
        self.assertEqual(call["file_name"], zip_path.name)
        self.assertIn("file", _multipart_zip_body(zip_bytes, zip_path.name)[0].decode("latin-1"))

    def test_preview_success_triggers_confirm_with_skip_policy(self) -> None:
        session_id, export_id, _zip_path = self._export_session()
        client = RecordingBackendClient(
            preview=_preview_response(export_id=export_id),
            confirm=_confirm_response(export_id=export_id),
        )
        upload_session_package(
            capture_session_id=session_id,
            inventory_id=self.context.inventory_id,
            upload_store=self.upload_store,
            backend_client=client,
        )
        self.assertEqual(len(client.confirm_calls), 1)
        self.assertEqual(client.confirm_calls[0]["export_id"], export_id)
        self.assertEqual(client.confirm_calls[0]["conflict_policy"], "SKIP")

    def test_rejected_preview_never_calls_confirm(self) -> None:
        session_id, export_id, _ = self._export_session()
        client = RecordingBackendClient(
            preview_error=InventoryBackendClientError(
                "PREVIEW_NOT_READY",
                "bad",
            ),
        )
        with self.assertRaises(PackageUploadError):
            upload_session_package(
                capture_session_id=session_id,
                inventory_id=self.context.inventory_id,
                upload_store=self.upload_store,
                backend_client=client,
            )
        self.assertEqual(client.confirm_calls, [])
        record = self.upload_store.load(session_id)
        assert record is not None
        self.assertEqual(record.state, "FAILED")

    def test_timeout_leaves_state_not_confirmed(self) -> None:
        session_id, export_id, _ = self._export_session()
        client = RecordingBackendClient(
            preview_error=InventoryBackendClientError("BACKEND_TIMEOUT", "timed out"),
        )
        with self.assertRaises(PackageUploadError):
            upload_session_package(
                capture_session_id=session_id,
                inventory_id=self.context.inventory_id,
                upload_store=self.upload_store,
                backend_client=client,
            )
        record = self.upload_store.load(session_id)
        assert record is not None
        self.assertNotEqual(record.state, "CONFIRMED")

    def test_auth_forbidden_surfaces_explicit_code(self) -> None:
        session_id, _, _ = self._export_session()
        client = RecordingBackendClient(
            preview_error=InventoryBackendClientError(
                "BACKEND_AUTH_FORBIDDEN",
                "forbidden",
                http_status=403,
            ),
        )
        with self.assertRaises(PackageUploadError) as ctx:
            upload_session_package(
                capture_session_id=session_id,
                inventory_id=self.context.inventory_id,
                upload_store=self.upload_store,
                backend_client=client,
            )
        self.assertEqual(ctx.exception.code, "BACKEND_AUTH_FORBIDDEN")

    def test_export_id_conflict_from_backend(self) -> None:
        session_id, _, _ = self._export_session()
        client = RecordingBackendClient(
            preview_error=InventoryBackendClientError(
                "LOCAL_INVENTORY_PACKAGE_EXPORT_CONFLICT",
                "export conflict",
                http_status=409,
            ),
        )
        with self.assertRaises(PackageUploadError) as ctx:
            upload_session_package(
                capture_session_id=session_id,
                inventory_id=self.context.inventory_id,
                upload_store=self.upload_store,
                backend_client=client,
            )
        self.assertEqual(ctx.exception.code, "LOCAL_INVENTORY_PACKAGE_EXPORT_CONFLICT")
        self.assertEqual(client.confirm_calls, [])

    def test_invalid_preview_response_blocks_confirm(self) -> None:
        session_id, export_id, _ = self._export_session()
        bad_preview = PackageApiResponse(
            raw={
                "export_id": export_id,
                "package_id": "pkg-1",
                "inventory_id": "inventory-1",
                "status": "MATERIALIZING",
            },
            package_id="pkg-1",
            export_id=export_id,
            inventory_id="inventory-1",
            status="MATERIALIZING",
            duplicate=False,
        )
        client = RecordingBackendClient(preview=bad_preview)
        with self.assertRaises(PackageUploadError):
            upload_session_package(
                capture_session_id=session_id,
                inventory_id=self.context.inventory_id,
                upload_store=self.upload_store,
                backend_client=client,
            )
        self.assertEqual(client.confirm_calls, [])

    def test_confirm_failure_keeps_local_zip(self) -> None:
        session_id, export_id, zip_path = self._export_session()
        client = RecordingBackendClient(
            preview=_preview_response(export_id=export_id),
            confirm_error=InventoryBackendClientError("CONFIRM_REJECTED", "nope"),
        )
        with self.assertRaises(PackageUploadError):
            upload_session_package(
                capture_session_id=session_id,
                inventory_id=self.context.inventory_id,
                upload_store=self.upload_store,
                backend_client=client,
            )
        self.assertTrue(zip_path.is_file())
        record = self.upload_store.load(session_id)
        assert record is not None
        self.assertEqual(record.state, "FAILED")

    def test_previewed_restart_skips_preview_and_confirms(self) -> None:
        session_id, export_id, _ = self._export_session()
        record = self.upload_store.load(session_id)
        assert record is not None
        self.upload_store.save(
            PackageUploadRecord(
                capture_session_id=session_id,
                export_id=export_id,
                inventory_id=record.inventory_id,
                aisle_id=record.aisle_id,
                zip_path=record.zip_path,
                state="PREVIEWED",
                package_id="pkg-1",
                error=None,
                previewed_at="2026-01-01T00:00:00+00:00",
                confirmed_at=None,
            )
        )
        client = RecordingBackendClient(
            confirm=_confirm_response(export_id=export_id),
        )
        outcome = upload_session_package(
            capture_session_id=session_id,
            inventory_id=self.context.inventory_id,
            upload_store=self.upload_store,
            backend_client=client,
        )
        self.assertTrue(outcome.preview_skipped)
        self.assertEqual(client.preview_calls, [])
        self.assertEqual(len(client.confirm_calls), 1)

    def test_confirm_success_persists_confirmed_state(self) -> None:
        session_id, export_id, _ = self._export_session()
        client = RecordingBackendClient(
            preview=_preview_response(export_id=export_id),
            confirm=_confirm_response(export_id=export_id),
        )
        upload_session_package(
            capture_session_id=session_id,
            inventory_id=self.context.inventory_id,
            upload_store=self.upload_store,
            backend_client=client,
        )
        record = self.upload_store.load(session_id)
        assert record is not None
        self.assertEqual(record.state, "CONFIRMED")
        self.assertEqual(record.package_id, "pkg-1")
        self.assertIsNotNone(record.confirmed_at)

    def test_reexport_reuses_zip_and_export_id(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        first = ensure_session_package_exported(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
            upload_store=self.upload_store,
        )
        second = ensure_session_package_exported(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
            upload_store=self.upload_store,
        )
        self.assertTrue(second.reused_existing_zip)
        self.assertEqual(first.export_id, second.export_id)
        self.assertEqual(first.zip_path, second.zip_path)

    def test_upload_does_not_delete_session_or_zip(self) -> None:
        session_id, export_id, zip_path = self._export_session()
        sessions_dir = self.root / "sessions"
        client = RecordingBackendClient(
            preview=_preview_response(export_id=export_id),
            confirm=_confirm_response(export_id=export_id),
        )
        upload_session_package(
            capture_session_id=session_id,
            inventory_id=self.context.inventory_id,
            upload_store=self.upload_store,
            backend_client=client,
        )
        self.assertTrue(zip_path.is_file())
        self.assertTrue(any(sessions_dir.iterdir()))

    def test_capture_export_offline_until_upload_requested(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        outcome = ensure_session_package_exported(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
            upload_store=self.upload_store,
        )
        self.assertTrue(outcome.zip_path.is_file())
        client = RecordingBackendClient()
        with self.assertRaises(PackageUploadError) as ctx:
            upload_session_package(
                capture_session_id="missing-session-id",
                inventory_id=self.context.inventory_id,
                upload_store=self.upload_store,
                backend_client=client,
            )
        self.assertEqual(ctx.exception.code, "PACKAGE_NOT_EXPORTED")
        self.assertEqual(client.preview_calls, [])

    def test_confirmed_state_not_downgraded_by_late_failure(self) -> None:
        session_id, export_id, zip_path = self._export_session()
        self.upload_store.save(
            PackageUploadRecord(
                capture_session_id=session_id,
                export_id=export_id,
                inventory_id="inventory-1",
                aisle_id="aisle-1",
                zip_path=str(zip_path),
                state="CONFIRMED",
                package_id="pkg-confirmed",
                error=None,
                previewed_at="2026-01-01T00:00:00+00:00",
                confirmed_at="2026-01-01T00:00:01+00:00",
            )
        )
        client = RecordingBackendClient(
            preview_error=InventoryBackendClientError("BACKEND_TIMEOUT", "late"),
        )
        outcome = upload_session_package(
            capture_session_id=session_id,
            inventory_id=self.context.inventory_id,
            upload_store=self.upload_store,
            backend_client=client,
        )
        self.assertEqual(outcome.upload_state, "CONFIRMED")
        record = self.upload_store.load(session_id)
        assert record is not None
        self.assertEqual(record.state, "CONFIRMED")

    def test_concurrent_exports_reuse_single_export_identity(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        results: list[str] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                outcome = ensure_session_package_exported(
                    session_store=store,
                    photos_root=photos_root,
                    output_directory=self.out,
                    capture_session_id=session_id,
                    context=self.context,
                    upload_store=self.upload_store,
                )
                results.append(outcome.export_id)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])

    def test_invalid_json_from_backend(self) -> None:
        session_id, _, _ = self._export_session()
        client = RecordingBackendClient(
            preview_error=InventoryBackendClientError(
                "BACKEND_INVALID_JSON",
                "invalid",
            ),
        )
        with self.assertRaises(PackageUploadError):
            upload_session_package(
                capture_session_id=session_id,
                inventory_id=self.context.inventory_id,
                upload_store=self.upload_store,
                backend_client=client,
            )
        self.assertEqual(client.confirm_calls, [])


class RaspberryPackageUseCaseIntegrationTest(unittest.TestCase):
    """Raspberry ZIP → PreviewLocalInventoryPackage → ConfirmLocalInventoryPackage (no HTTP mock)."""

    def test_raspberry_zip_preview_and_confirm_use_cases(self) -> None:
        from datetime import datetime, timezone

        try:
            from src.application.use_cases.inventories.manage_local_csv_import import (
                PreviewLocalCsvImport,
            )
            from src.application.use_cases.inventories.manage_local_inventory_package import (
                ConfirmLocalInventoryPackage,
                PreviewLocalInventoryPackage,
            )
        except ModuleNotFoundError as exc:
            self.skipTest(
                f"Backend integration dependencies unavailable in this environment: {exc}"
            )

        from src.application.services.aisle_source_asset_materializer import (
            AisleSourceAssetMaterializer,
        )
        from src.application.services.inventory_status_reconciler import (
            InventoryStatusReconciler,
        )
        from src.application.services.local_csv_position_materializer import (
            LocalCsvPositionMaterializer,
        )
        from src.application.services.product_labels.issued_product_label_resolver import (
            IssuedProductLabelResolver,
        )
        from src.domain.aisle.entities import Aisle, AisleStatus
        from src.domain.inventory.entities import Inventory, InventoryStatus
        from src.infrastructure.repositories.local_csv_inventory_result_writer import (
            MemoryLocalCsvInventoryResultWriter,
        )
        from src.infrastructure.repositories.memory_aisle_repository import (
            MemoryAisleRepository,
        )
        from src.infrastructure.repositories.memory_inventory_counted_product_label_repository import (
            MemoryInventoryCountedProductLabelRepository,
        )
        from src.infrastructure.repositories.memory_inventory_repository import (
            MemoryInventoryRepository,
        )
        from src.infrastructure.repositories.memory_issued_product_label_repository import (
            MemoryIssuedProductLabelRepository,
        )
        from src.infrastructure.repositories.memory_local_csv_import_repository import (
            MemoryLocalCsvImportRepository,
        )
        from src.infrastructure.repositories.memory_local_inventory_package_repository import (
            MemoryLocalInventoryPackageRepository,
        )
        from src.infrastructure.repositories.memory_position_repository import (
            MemoryPositionRepository,
        )
        from src.infrastructure.repositories.memory_product_record_repository import (
            MemoryProductRecordRepository,
        )
        from src.infrastructure.repositories.memory_source_asset_repository import (
            MemorySourceAssetRepository,
        )
        from session_package_export import export_finished_session_package

        root = Path(tempfile.mkdtemp())
        out = root / "packages"
        upload_store = PackageUploadStore(root / "upload-state")
        context = SessionPackageExportContext(
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            device_id="device-rpi-1",
        )
        _, store, photos_root, session_id = build_finished_session(root)
        export_result = export_finished_session_package(
            session_store=store,
            photos_root=photos_root,
            output_directory=out,
            capture_session_id=session_id,
            context=context,
        )
        zip_bytes = export_result.zip_path.read_bytes()

        NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

        class FixedClock:
            def now(self) -> datetime:
                return NOW

        class MemoryArtifactStorage:
            def put_object(self, key: str, file_obj, content_type: str):
                data = file_obj.read()

                class Stored:
                    storage_provider = "local"
                    storage_bucket = None
                    storage_key = key
                    content_type = content_type
                    file_size_bytes = len(data)
                    etag = "etag"

                return Stored()

        inventory_repo = MemoryInventoryRepository()
        aisle_repo = MemoryAisleRepository()
        inventory_repo.save(
            Inventory(
                id="inventory-1",
                client_id="client-a",
                name="Inv",
                status=InventoryStatus.DRAFT,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        aisle_repo.save(
            Aisle(
                id="aisle-1",
                inventory_id="inventory-1",
                code="A1",
                status=AisleStatus.CREATED,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        csv_repo = MemoryLocalCsvImportRepository()
        package_repo = MemoryLocalInventoryPackageRepository(csv_import_repo=csv_repo)
        clock = FixedClock()
        csv_preview = PreviewLocalCsvImport(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            import_repo=csv_repo,
            clock=clock,
            enabled=True,
        )
        preview_uc = PreviewLocalInventoryPackage(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            csv_import_repo=csv_repo,
            package_repo=package_repo,
            csv_preview=csv_preview,
            clock=clock,
            enabled=True,
            staging_root=root / "staging",
        )
        packaged = preview_uc.execute(inventory_id="inventory-1", content=zip_bytes)
        self.assertEqual(packaged.status, "PREVIEWED")

        asset_repo = MemorySourceAssetRepository()
        storage = MemoryArtifactStorage()
        materializer = AisleSourceAssetMaterializer(
            aisle_repo=aisle_repo,
            asset_repo=asset_repo,
            artifact_storage=storage,  # type: ignore[arg-type]
            status_reconciler=InventoryStatusReconciler(
                inventory_repo=inventory_repo,
                aisle_repo=aisle_repo,
                clock=clock,
            ),
        )
        writer = MemoryLocalCsvInventoryResultWriter(
            get_import_status=lambda import_id: (
                None
                if (rec := csv_repo.get_by_id(import_id)) is None
                else rec.status
            ),
        )
        position_repo = MemoryPositionRepository()
        product_repo = MemoryProductRecordRepository()
        confirm_uc = ConfirmLocalInventoryPackage(
            package_repo=package_repo,
            result_writer=writer,
            materializer=materializer,
            aisle_repo=aisle_repo,
            inventory_repo=inventory_repo,
            clock=clock,
            enabled=True,
            position_materializer=LocalCsvPositionMaterializer(
                position_repo=position_repo,
                product_record_repo=product_repo,
                counted_product_label_repo=MemoryInventoryCountedProductLabelRepository(),
                issued_label_resolver=IssuedProductLabelResolver(
                    issued_repo=MemoryIssuedProductLabelRepository()
                ),
                inventory_repo=inventory_repo,
            ),
        )
        confirmed, duplicate = confirm_uc.execute(
            inventory_id="inventory-1",
            export_id=export_result.export_id,
            conflict_policy="SKIP",
            confirmed_by_user_id="raspberry-scanner",
        )
        self.assertFalse(duplicate)
        self.assertEqual(confirmed.status, "CONFIRMED")

        ensure_session_package_exported(
            session_store=store,
            photos_root=photos_root,
            output_directory=out,
            capture_session_id=session_id,
            context=context,
            upload_store=upload_store,
        )
        client = RecordingBackendClient(
            preview=_preview_response(export_id=export_result.export_id),
            confirm=_confirm_response(export_id=export_result.export_id, duplicate=True),
        )
        outcome = upload_session_package(
            capture_session_id=session_id,
            inventory_id=context.inventory_id,
            upload_store=upload_store,
            backend_client=client,
        )
        self.assertEqual(outcome.upload_state, "CONFIRMED")


class BackendHttpIntegrationTest(unittest.TestCase):
    def test_http_preview_confirm_when_env_configured(self) -> None:
        if os.environ.get("DINAMIC_RUN_BACKEND_HTTP_INTEGRATION") != "1":
            self.skipTest(
                "Set DINAMIC_RUN_BACKEND_HTTP_INTEGRATION=1 with backend URL/token to run HTTP integration"
            )
        from inventory_backend_client import inventory_backend_client_from_environment
        from session_package_upload import build_backend_client_from_environment

        try:
            build_backend_client_from_environment()
        except InventoryBackendClientError as exc:
            self.skipTest(f"Backend HTTP integration not configured: {exc}")
        self.skipTest(
            "HTTP integration requires a pre-exported session id in env; use unit/use-case tests by default"
        )


if __name__ == "__main__":
    unittest.main()
