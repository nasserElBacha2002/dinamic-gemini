"""SQL Server integration tests for package/CSV confirm transaction boundaries."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.application.services.aisle_source_asset_materializer import AisleSourceAssetMaterializer
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.local_csv_position_materializer import LocalCsvPositionMaterializer
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.application.use_cases.inventories.manage_local_csv_import import (
    ConfirmLocalCsvImport,
    LocalCsvImportError,
    PreviewLocalCsvImport,
)
from src.application.use_cases.inventories.manage_local_inventory_package import (
    ConfirmLocalInventoryPackage,
    PreviewLocalInventoryPackage,
)
from src.database.sqlserver import SqlServerClient
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.local_inventory_package.errors import LocalInventoryPackageImportError
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    SqlLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_counted_product_label_repository import (
    SqlInventoryCountedProductLabelRepository,
)
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_issued_product_label_repository import (
    SqlIssuedProductLabelRepository,
)
from src.infrastructure.repositories.sql_local_csv_import_repository import (
    SqlLocalCsvImportRepository,
)
from src.infrastructure.repositories.sql_local_inventory_package_repository import (
    SqlLocalInventoryPackageRepository,
)
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_product_record_repository import SqlProductRecordRepository
from src.infrastructure.repositories.sql_source_asset_repository import SqlSourceAssetRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests
from tests.unit.test_local_inventory_package import JPEG_BYTES

pytestmark = pytest.mark.integration

HEADERS = (
    "schema_version",
    "export_id",
    "exported_at",
    "device_id",
    "inventory_id",
    "aisle_id",
    "capture_session_id",
    "capture_photo_id",
    "client_file_id",
    "capture_order",
    "captured_at",
    "position_code",
    "internal_code",
    "quantity",
    "quantity_status",
    "detection_status",
    "source",
    "requires_review",
    "error_code",
    "notes",
)


class FixedClock:
    def __init__(self, moment: datetime | None = None) -> None:
        self._moment = moment or datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._moment


class MemoryArtifactStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, key: str, file_obj, content_type: str):
        data = file_obj.read()
        self.objects[key] = data
        mime = content_type

        class Stored:
            storage_provider = "local"
            storage_bucket = None
            storage_key = key
            content_type = mime
            file_size_bytes = len(data)
            etag = hashlib.sha256(data).hexdigest()

        return Stored()

    def save_file(self, key: str, file_obj, content_type: str) -> None:
        self.objects[key] = file_obj.read()

    def delete_file(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.fixture(scope="module")
def sql_client():
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    return client


@pytest.fixture(scope="module")
def connection_string(sql_client):
    return sql_client.connection_string


def _csv_bytes(
    *,
    inventory_id: str,
    aisle_id: str,
    export_id: str,
    session_id: str = "session-1",
    photo_id: str = "photo-1",
    client_file_id: str = "file-1",
) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(
        {
            "schema_version": "1",
            "export_id": export_id,
            "exported_at": "2026-08-04T10:00:00Z",
            "device_id": "device-1",
            "inventory_id": inventory_id,
            "aisle_id": aisle_id,
            "capture_session_id": session_id,
            "capture_photo_id": photo_id,
            "client_file_id": client_file_id,
            "capture_order": "1",
            "captured_at": "2026-08-04T09:59:00Z",
            "position_code": "A-01",
            "internal_code": "SKU-1",
            "quantity": "7",
            "quantity_status": "PRESENT",
            "detection_status": "DETECTED",
            "source": "LOCAL_CODE_SCAN",
            "requires_review": "false",
            "error_code": "",
            "notes": "ok",
        }
    )
    return output.getvalue().encode()


def _build_zip(
    *,
    inventory_id: str,
    aisle_id: str,
    export_id: str,
    session_id: str = "session-1",
    photo_id: str = "photo-1",
    client_file_id: str = "file-1",
) -> bytes:
    csv_bytes = _csv_bytes(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        export_id=export_id,
        session_id=session_id,
        photo_id=photo_id,
        client_file_id=client_file_id,
    )
    file_name = f"0001_{photo_id}.jpg"
    sha = hashlib.sha256(JPEG_BYTES).hexdigest()
    manifest = {
        "package_kind": "DINAMIC_LOCAL_AISLE_EXPORT",
        "package_version": 2,
        "status": "COMPLETE",
        "export_id": export_id,
        "inventory_id": inventory_id,
        "aisle_id": aisle_id,
        "capture_session_id": session_id,
        "freeze_id": "freeze-1",
        "row_count": 1,
        "expected_photo_count": 1,
        "included_photo_count": 1,
        "csv_checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "package_checksum_sha256": "abc",
        "photos": [
            {
                "capture_photo_id": photo_id,
                "client_file_id": client_file_id,
                "sequence_number": 1,
                "file_name": file_name,
                "mime_type": "image/jpeg",
                "size_bytes": len(JPEG_BYTES),
                "sha256": sha,
                "width": 1,
                "height": 1,
                "asset_variant": "ORIGINAL",
            }
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("results.csv", csv_bytes)
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr(f"photos/{file_name}", JPEG_BYTES)
    return buf.getvalue()


def _seed_inventory_and_aisle(client: SqlServerClient) -> tuple[str, str]:
    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    now = datetime.now(timezone.utc)
    inv_id = f"inv-pkg-{uuid.uuid4().hex[:10]}"
    aisle_id = f"aisle-pkg-{uuid.uuid4().hex[:10]}"
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Package confirm SQL",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"A-{uuid.uuid4().hex[:6]}",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    return inv_id, aisle_id


def _build_stack(
    client: SqlServerClient,
    *,
    staging_root: Path,
    clock: FixedClock | None = None,
) -> dict[str, object]:
    clock = clock or FixedClock()
    csv_repo = SqlLocalCsvImportRepository(client)
    package_repo = SqlLocalInventoryPackageRepository(client, csv_import_repo=csv_repo)
    writer = SqlLocalCsvInventoryResultWriter(client)
    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    asset_repo = SqlSourceAssetRepository(client)
    storage = MemoryArtifactStorage()
    materializer = AisleSourceAssetMaterializer(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,  # type: ignore[arg-type]
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inv_repo,
            aisle_repo=aisle_repo,
            clock=clock,
        ),
    )
    position_materializer = LocalCsvPositionMaterializer(
        position_repo=SqlPositionRepository(client),
        product_record_repo=SqlProductRecordRepository(client),
        counted_product_label_repo=SqlInventoryCountedProductLabelRepository(client),
        issued_label_resolver=IssuedProductLabelResolver(
            issued_repo=SqlIssuedProductLabelRepository(client)
        ),
        inventory_repo=inv_repo,
    )
    csv_preview = PreviewLocalCsvImport(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        import_repo=csv_repo,
        clock=clock,
        enabled=True,
    )
    preview = PreviewLocalInventoryPackage(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=package_repo,
        csv_preview=csv_preview,
        clock=clock,
        enabled=True,
        staging_root=staging_root,
    )
    confirm = ConfirmLocalInventoryPackage(
        package_repo=package_repo,
        result_writer=writer,
        materializer=materializer,
        aisle_repo=aisle_repo,
        clock=clock,
        enabled=True,
        position_materializer=position_materializer,
    )
    csv_confirm = ConfirmLocalCsvImport(
        import_repo=csv_repo,
        result_writer=writer,
        clock=clock,
        enabled=True,
        position_materializer=position_materializer,
        aisle_repo=aisle_repo,
    )
    return {
        "preview": preview,
        "confirm": confirm,
        "csv_preview": csv_preview,
        "csv_confirm": csv_confirm,
        "package_repo": package_repo,
        "csv_repo": csv_repo,
        "writer": writer,
        "asset_repo": asset_repo,
        "materializer": materializer,
        "aisle_repo": aisle_repo,
        "storage": storage,
    }


def _preview_package(
    stack: dict[str, object],
    *,
    inventory_id: str,
    aisle_id: str,
    export_id: str,
    session_id: str = "session-1",
    photo_id: str = "photo-1",
):
    preview = stack["preview"]
    assert isinstance(preview, PreviewLocalInventoryPackage)
    return preview.execute(
        inventory_id=inventory_id,
        content=_build_zip(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            export_id=export_id,
            session_id=session_id,
            photo_id=photo_id,
        ),
    )


def _count_productive(client: SqlServerClient, inventory_id: str) -> int:
    with client.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM local_csv_productive_results WHERE inventory_id = ?",
            (inventory_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


def _fresh_read_statuses(
    connection_string: str,
    *,
    inventory_id: str,
    export_id: str,
) -> tuple[str | None, str | None, int]:
    verify = SqlServerClient(connection_string)
    with verify.cursor() as cur:
        cur.execute(
            "SELECT status FROM local_inventory_packages "
            "WHERE inventory_id = ? AND export_id = ?",
            (inventory_id, export_id),
        )
        pkg_row = cur.fetchone()
        cur.execute(
            "SELECT status FROM local_csv_imports WHERE inventory_id = ? AND export_id = ?",
            (inventory_id, export_id),
        )
        csv_row = cur.fetchone()
        cur.execute(
            "SELECT COUNT(*) FROM local_csv_productive_results WHERE inventory_id = ?",
            (inventory_id,),
        )
        productive_row = cur.fetchone()
    return (
        str(pkg_row.status) if pkg_row else None,
        str(csv_row.status) if csv_row else None,
        int(productive_row[0]) if productive_row else 0,
    )


@contextmanager
def _fail_on_package_status_update():
    """Fail after CSV confirm persist, before package CONFIRMED update (same TX)."""
    import src.infrastructure.repositories.sql_local_inventory_package_repository as pkg_mod

    original = pkg_mod.sql_repository_cursor

    class _CursorProxy:
        def __init__(self, cur: object) -> None:
            self._cur = cur

        def execute(self, stmt, *args, **kwargs):
            if "UPDATE local_inventory_packages SET status" in str(stmt):
                raise RuntimeError("injected package status update failure")
            return self._cur.execute(stmt, *args, **kwargs)  # type: ignore[attr-defined]

        def __getattr__(self, name: str):
            return getattr(self._cur, name)

    @contextmanager
    def patched(client, connection=None):
        with original(client, connection=connection) as cur:
            yield _CursorProxy(cur)

    pkg_mod.sql_repository_cursor = patched  # type: ignore[assignment]
    try:
        yield
    finally:
        pkg_mod.sql_repository_cursor = original  # type: ignore[assignment]


def test_a_happy_path_confirm_from_new_connection(
    sql_client, connection_string, tmp_path
) -> None:
    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    export_id = f"export-a-{uuid.uuid4().hex[:8]}"
    stack = _build_stack(sql_client, staging_root=tmp_path / "a")
    _preview_package(
        stack, inventory_id=inventory_id, aisle_id=aisle_id, export_id=export_id
    )
    confirm = stack["confirm"]
    assert isinstance(confirm, ConfirmLocalInventoryPackage)

    confirmed, duplicate = confirm.execute(
        inventory_id=inventory_id,
        export_id=export_id,
        confirmed_by_user_id="user-a",
    )
    assert duplicate is False
    assert confirmed.status == "CONFIRMED"

    pkg_status, csv_status, productive_count = _fresh_read_statuses(
        connection_string, inventory_id=inventory_id, export_id=export_id
    )
    assert pkg_status == "CONFIRMED"
    assert csv_status == "CONFIRMED"
    assert productive_count >= 1


def test_b_productive_failure_rolls_back_package_and_csv(
    sql_client, tmp_path
) -> None:
    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    export_id = f"export-b-{uuid.uuid4().hex[:8]}"
    stack = _build_stack(sql_client, staging_root=tmp_path / "b")
    pkg = _preview_package(
        stack, inventory_id=inventory_id, aisle_id=aisle_id, export_id=export_id
    )
    confirm = stack["confirm"]
    assert isinstance(confirm, ConfirmLocalInventoryPackage)
    writer = stack["writer"]
    assert isinstance(writer, SqlLocalCsvInventoryResultWriter)

    def boom(*_args, **_kwargs):
        raise RuntimeError("injected productive failure")

    writer.apply_import = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="injected productive failure"):
        confirm.execute(
            inventory_id=inventory_id,
            export_id=export_id,
            confirmed_by_user_id="user-b",
        )

    package_repo = stack["package_repo"]
    csv_repo = stack["csv_repo"]
    assert isinstance(package_repo, SqlLocalInventoryPackageRepository)
    assert isinstance(csv_repo, SqlLocalCsvImportRepository)
    again = package_repo.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
    assert again is not None and again.status == "PREVIEWED"
    csv = csv_repo.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
    assert csv is not None and csv.status == "PREVIEWED"
    assert _count_productive(sql_client, inventory_id) == 0
    assert pkg.export_id == export_id


def test_c_failure_after_csv_before_package_update_rolls_back(
    sql_client, tmp_path
) -> None:
    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    export_id = f"export-c-{uuid.uuid4().hex[:8]}"
    stack = _build_stack(sql_client, staging_root=tmp_path / "c")
    _preview_package(stack, inventory_id=inventory_id, aisle_id=aisle_id, export_id=export_id)
    confirm = stack["confirm"]
    assert isinstance(confirm, ConfirmLocalInventoryPackage)

    with _fail_on_package_status_update():
        with pytest.raises(RuntimeError, match="injected package status update failure"):
            confirm.execute(
                inventory_id=inventory_id,
                export_id=export_id,
                confirmed_by_user_id="user-c",
            )

    package_repo = stack["package_repo"]
    csv_repo = stack["csv_repo"]
    assert isinstance(package_repo, SqlLocalInventoryPackageRepository)
    assert isinstance(csv_repo, SqlLocalCsvImportRepository)
    pkg = package_repo.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
    csv = csv_repo.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
    assert pkg is not None and pkg.status == "PREVIEWED"
    assert csv is not None and csv.status == "PREVIEWED"
    assert _count_productive(sql_client, inventory_id) == 0


def test_d_concurrent_double_confirm_one_winner(
    connection_string, tmp_path
) -> None:
    """Two real SQL connections race package confirm; TX winner + idempotent loser.

    Position materializer is disabled here so the assertion targets the confirm TX
    (not concurrent post-commit derivation races on product_records).
    """
    client_seed = SqlServerClient(connection_string)
    inventory_id, aisle_id = _seed_inventory_and_aisle(client_seed)
    export_id = f"export-d-{uuid.uuid4().hex[:8]}"
    staging = tmp_path / "d"
    stack_seed = _build_stack(client_seed, staging_root=staging)
    # Rebuild confirm without position materializer for this concurrency case.
    stack_seed["confirm"] = ConfirmLocalInventoryPackage(
        package_repo=stack_seed["package_repo"],  # type: ignore[arg-type]
        result_writer=stack_seed["writer"],  # type: ignore[arg-type]
        materializer=stack_seed["materializer"],  # type: ignore[arg-type]
        aisle_repo=stack_seed["aisle_repo"],  # type: ignore[arg-type]
        clock=FixedClock(),
        enabled=True,
        position_materializer=None,
    )
    _preview_package(
        stack_seed, inventory_id=inventory_id, aisle_id=aisle_id, export_id=export_id
    )

    results: list[tuple[str, bool]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        client = SqlServerClient(connection_string)
        stack = _build_stack(client, staging_root=staging)
        confirm = ConfirmLocalInventoryPackage(
            package_repo=stack["package_repo"],  # type: ignore[arg-type]
            result_writer=stack["writer"],  # type: ignore[arg-type]
            materializer=stack["materializer"],  # type: ignore[arg-type]
            aisle_repo=stack["aisle_repo"],  # type: ignore[arg-type]
            clock=FixedClock(),
            enabled=True,
            position_materializer=None,
        )
        try:
            barrier.wait(timeout=10)
            confirmed, duplicate = confirm.execute(
                inventory_id=inventory_id,
                export_id=export_id,
                confirmed_by_user_id="user-d",
            )
            results.append((confirmed.status, duplicate))
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(results) == 2
    assert sum(1 for _, dup in results if dup is False) == 1
    assert sum(1 for _, dup in results if dup is True) == 1
    pkg_status, csv_status, productive_count = _fresh_read_statuses(
        connection_string, inventory_id=inventory_id, export_id=export_id
    )
    assert pkg_status == "CONFIRMED"
    assert csv_status == "CONFIRMED"
    assert productive_count == 1


def test_e_reconfirm_does_not_add_productive(sql_client, tmp_path) -> None:
    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    export_id = f"export-e-{uuid.uuid4().hex[:8]}"
    stack = _build_stack(sql_client, staging_root=tmp_path / "e")
    _preview_package(stack, inventory_id=inventory_id, aisle_id=aisle_id, export_id=export_id)
    confirm = stack["confirm"]
    assert isinstance(confirm, ConfirmLocalInventoryPackage)

    confirm.execute(
        inventory_id=inventory_id,
        export_id=export_id,
        confirmed_by_user_id="user-e",
    )
    count_after_first = _count_productive(sql_client, inventory_id)
    _, duplicate = confirm.execute(
        inventory_id=inventory_id,
        export_id=export_id,
        confirmed_by_user_id="user-e",
    )
    assert duplicate is True
    assert _count_productive(sql_client, inventory_id) == count_after_first


def test_f_invalid_package_status_has_no_side_effects(sql_client, tmp_path) -> None:
    """Optimistic gate rejects non-PREVIEWED without storage/productive side effects.

    DB CHECK only allows PREVIEWED|CONFIRMED, so invalid status is simulated via
    get_by_export_id (application gate) without writing an illegal status row.
    """
    from dataclasses import replace

    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    export_id = f"export-f-{uuid.uuid4().hex[:8]}"
    stack = _build_stack(sql_client, staging_root=tmp_path / "f")
    pkg = _preview_package(
        stack, inventory_id=inventory_id, aisle_id=aisle_id, export_id=export_id
    )
    storage = stack["storage"]
    assert isinstance(storage, MemoryArtifactStorage)
    storage_before = len(storage.objects)

    package_repo = stack["package_repo"]
    assert isinstance(package_repo, SqlLocalInventoryPackageRepository)
    real_get = package_repo.get_by_export_id

    def get_invalid(*, inventory_id: str, export_id: str):
        current = real_get(inventory_id=inventory_id, export_id=export_id)
        assert current is not None
        return replace(current, status="CANCELLED")

    package_repo.get_by_export_id = get_invalid  # type: ignore[method-assign]

    confirm = stack["confirm"]
    assert isinstance(confirm, ConfirmLocalInventoryPackage)
    with pytest.raises(LocalInventoryPackageImportError) as exc:
        confirm.execute(
            inventory_id=inventory_id,
            export_id=export_id,
            confirmed_by_user_id="user-f",
        )
    assert exc.value.code == "PACKAGE_INVALID_STATUS"
    assert len(storage.objects) == storage_before
    assert _count_productive(sql_client, inventory_id) == 0

    package_repo.get_by_export_id = real_get  # type: ignore[method-assign]
    csv_repo = stack["csv_repo"]
    assert isinstance(csv_repo, SqlLocalCsvImportRepository)
    again = package_repo.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
    csv = csv_repo.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
    assert again is not None and again.status == "PREVIEWED"
    assert csv is not None and csv.status == "PREVIEWED"
    assert again.id == pkg.id


def test_g_csv_skip_conflict_marks_duplicate_without_extra_productive(
    sql_client, tmp_path
) -> None:
    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    session_id = f"session-g-{uuid.uuid4().hex[:6]}"
    photo_id = f"photo-g-{uuid.uuid4().hex[:6]}"
    stack = _build_stack(sql_client, staging_root=tmp_path / "g")
    csv_preview = stack["csv_preview"]
    csv_confirm = stack["csv_confirm"]
    assert isinstance(csv_preview, PreviewLocalCsvImport)
    assert isinstance(csv_confirm, ConfirmLocalCsvImport)

    first = csv_preview.execute(
        inventory_id=inventory_id,
        content=_csv_bytes(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            export_id=f"export-g1-{uuid.uuid4().hex[:6]}",
            session_id=session_id,
            photo_id=photo_id,
        ),
    )
    csv_confirm.execute(
        inventory_id=inventory_id,
        export_id=first.export_id,
        confirmed_by_user_id="user-g1",
    )
    assert _count_productive(sql_client, inventory_id) == 1

    second = csv_preview.execute(
        inventory_id=inventory_id,
        content=_csv_bytes(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            export_id=f"export-g2-{uuid.uuid4().hex[:6]}",
            session_id=session_id,
            photo_id=photo_id,
        ),
    )
    confirmed, duplicate = csv_confirm.execute(
        inventory_id=inventory_id,
        export_id=second.export_id,
        conflict_policy="SKIP",
        confirmed_by_user_id="user-g2",
    )
    assert duplicate is False
    assert confirmed.duplicate_rows == 1
    assert confirmed.rows[0].status == "DUPLICATE"
    assert _count_productive(sql_client, inventory_id) == 1


def test_h_csv_reject_conflict_raises_without_productive_leftovers(
    sql_client, tmp_path
) -> None:
    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    session_id = f"session-h-{uuid.uuid4().hex[:6]}"
    photo_id = f"photo-h-{uuid.uuid4().hex[:6]}"
    stack = _build_stack(sql_client, staging_root=tmp_path / "h")
    csv_preview = stack["csv_preview"]
    csv_confirm = stack["csv_confirm"]
    assert isinstance(csv_preview, PreviewLocalCsvImport)
    assert isinstance(csv_confirm, ConfirmLocalCsvImport)

    first = csv_preview.execute(
        inventory_id=inventory_id,
        content=_csv_bytes(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            export_id=f"export-h1-{uuid.uuid4().hex[:6]}",
            session_id=session_id,
            photo_id=photo_id,
        ),
    )
    csv_confirm.execute(
        inventory_id=inventory_id,
        export_id=first.export_id,
        confirmed_by_user_id="user-h1",
    )
    productive_after_first = _count_productive(sql_client, inventory_id)
    assert productive_after_first == 1

    second = csv_preview.execute(
        inventory_id=inventory_id,
        content=_csv_bytes(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            export_id=f"export-h2-{uuid.uuid4().hex[:6]}",
            session_id=session_id,
            photo_id=photo_id,
        ),
    )
    with pytest.raises(LocalCsvImportError) as exc:
        csv_confirm.execute(
            inventory_id=inventory_id,
            export_id=second.export_id,
            conflict_policy="REJECT",
            confirmed_by_user_id="user-h2",
        )
    assert exc.value.code == "LOCAL_CSV_SECONDARY_CONFLICT"
    assert _count_productive(sql_client, inventory_id) == productive_after_first

    csv_repo = stack["csv_repo"]
    assert isinstance(csv_repo, SqlLocalCsvImportRepository)
    still_previewed = csv_repo.get_by_export_id(
        inventory_id=inventory_id, export_id=second.export_id
    )
    assert still_previewed is not None and still_previewed.status == "PREVIEWED"
