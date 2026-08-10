"""Unit tests for local inventory ZIP package parse + preview/confirm."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.application.services.aisle_source_asset_materializer import AisleSourceAssetMaterializer
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.local_csv_position_materializer import LocalCsvPositionMaterializer
from src.application.services.local_inventory_package_parser import (
    LocalInventoryPackageError,
    parse_local_inventory_package,
)
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.application.use_cases.inventories.manage_local_csv_import import PreviewLocalCsvImport
from src.application.use_cases.inventories.manage_local_inventory_package import (
    ConfirmLocalInventoryPackage,
    PreviewLocalInventoryPackage,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.local_inventory_package.errors import LocalInventoryPackageImportError
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    MemoryLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_counted_product_label_repository import (
    MemoryInventoryCountedProductLabelRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_issued_product_label_repository import (
    MemoryIssuedProductLabelRepository,
)
from src.infrastructure.repositories.memory_local_csv_import_repository import (
    MemoryLocalCsvImportRepository,
)
from src.infrastructure.repositories.memory_local_inventory_package_repository import (
    MemoryLocalInventoryPackageRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)

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
NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)


class FixedClock:
    def now(self) -> datetime:
        return NOW


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


def _csv_bytes(
    *,
    export_id: str = "export-pkg-1",
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
            "inventory_id": "inventory-1",
            "aisle_id": "aisle-1",
            "capture_session_id": "session-1",
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
    export_id: str = "export-pkg-1",
    photo_id: str = "photo-1",
    client_file_id: str = "file-1",
    photo_bytes: bytes = JPEG_BYTES,
    corrupt_sha: bool = False,
    omit_photo: bool = False,
) -> bytes:
    csv_bytes = _csv_bytes(export_id=export_id, photo_id=photo_id, client_file_id=client_file_id)
    file_name = f"0001_{photo_id}.jpg"
    sha = hashlib.sha256(photo_bytes).hexdigest()
    if corrupt_sha:
        sha = "0" * 64
    manifest = {
        "package_kind": "DINAMIC_LOCAL_AISLE_EXPORT",
        "package_version": 2,
        "status": "COMPLETE",
        "export_id": export_id,
        "inventory_id": "inventory-1",
        "aisle_id": "aisle-1",
        "capture_session_id": "session-1",
        "freeze_id": "freeze-1",
        "row_count": 1,
        "expected_photo_count": 1,
        "included_photo_count": 0 if omit_photo else 1,
        "csv_checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "package_checksum_sha256": "abc",
        "photos": []
        if omit_photo
        else [
            {
                "capture_photo_id": photo_id,
                "client_file_id": client_file_id,
                "sequence_number": 1,
                "file_name": file_name,
                "mime_type": "image/jpeg",
                "size_bytes": len(photo_bytes),
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
        if not omit_photo:
            zf.writestr(f"photos/{file_name}", photo_bytes)
    return buf.getvalue()


def test_parse_rejects_checksum_mismatch() -> None:
    with pytest.raises(LocalInventoryPackageError) as exc:
        parse_local_inventory_package(_build_zip(corrupt_sha=True))
    assert exc.value.code == "PACKAGE_PHOTO_CHECKSUM_MISMATCH"


def test_parse_accepts_complete_package() -> None:
    parsed = parse_local_inventory_package(_build_zip())
    assert parsed.export_id == "export-pkg-1"
    assert parsed.included_photo_count == 1
    assert parsed.photos[0].sha256 == hashlib.sha256(JPEG_BYTES).hexdigest()


def test_preview_and_confirm_creates_source_assets(tmp_path: Path) -> None:
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
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
    preview = PreviewLocalInventoryPackage(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=package_repo,
        csv_preview=csv_preview,
        clock=clock,
        enabled=True,
        staging_root=tmp_path,
    )
    packaged = preview.execute(inventory_id="inventory-1", content=_build_zip())
    assert packaged.status == "PREVIEWED"
    assert packaged.included_photo_count == 1
    assert packaged.csv_import is not None
    assert packaged.csv_import.valid_rows == 1

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
    writer = MemoryLocalCsvInventoryResultWriter()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    confirm = ConfirmLocalInventoryPackage(
        package_repo=package_repo,
        result_writer=writer,
        materializer=materializer,
        aisle_repo=aisle_repo,
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
    confirmed, duplicate = confirm.execute(
        inventory_id="inventory-1",
        export_id="export-pkg-1",
        conflict_policy="SKIP",
        confirmed_by_user_id="user-1",
    )
    assert duplicate is False
    assert confirmed.status == "CONFIRMED"
    results = writer.list_for_inventory("inventory-1")
    assert len(results) == 1
    assert results[0].has_image_evidence is True
    assert results[0].source_asset_id is not None
    assets = asset_repo.list_by_aisle("aisle-1")
    assert len(assets) == 1
    assert assets[0].upload_client_file_id == "file-1"
    assert assets[0].upload_batch_id == confirmed.id
    assert len(assets[0].upload_batch_id or "") <= 36
    assert results[0].source_asset_id == assets[0].id

    positions = position_repo.list_by_aisle("aisle-1", job_id=None)
    assert len(positions) == 1
    assert positions[0].job_id is None
    assert positions[0].corrected_position_code == "A-01"
    assert positions[0].detected_summary_json is not None
    assert positions[0].detected_summary_json.get("source_image_id") == assets[0].id
    products = product_repo.list_by_position(positions[0].id)
    assert len(products) == 1
    assert products[0].sku == "SKU-1"

    aisle_after = aisle_repo.get_by_id("aisle-1")
    assert aisle_after is not None
    assert aisle_after.status == AisleStatus.PROCESSED

    # Re-confirm backfills positions idempotently for already-confirmed packages
    again, again_dup = confirm.execute(
        inventory_id="inventory-1",
        export_id="export-pkg-1",
        conflict_policy="SKIP",
        confirmed_by_user_id="user-1",
    )
    assert again_dup is True
    assert again.status == "CONFIRMED"
    assert len(position_repo.list_by_aisle("aisle-1", job_id=None)) == 1
    assert aisle_repo.get_by_id("aisle-1").status == AisleStatus.PROCESSED


def test_confirm_fits_long_mobile_client_file_id(tmp_path: Path) -> None:
    """Mobile ZIP uses session:media client_file_ids longer than VARCHAR(36)."""
    from src.application.services.local_inventory_package_client_file_id import (
        SOURCE_ASSET_UPLOAD_CLIENT_FILE_ID_MAX,
        fit_source_asset_upload_client_file_id,
    )

    long_cf = "fd2e9f97-babd-40f7-b059-87c2776e6969:1000329481"
    assert len(long_cf) > SOURCE_ASSET_UPLOAD_CLIENT_FILE_ID_MAX
    fitted = fit_source_asset_upload_client_file_id(long_cf, stable_key=long_cf)
    assert len(fitted) == SOURCE_ASSET_UPLOAD_CLIENT_FILE_ID_MAX
    assert fitted == fit_source_asset_upload_client_file_id(long_cf, stable_key=long_cf)

    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
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
    preview = PreviewLocalInventoryPackage(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=package_repo,
        csv_preview=csv_preview,
        clock=clock,
        enabled=True,
        staging_root=tmp_path,
    )
    packaged = preview.execute(
        inventory_id="inventory-1",
        content=_build_zip(
            export_id="export-long-cf",
            photo_id=long_cf,
            client_file_id=long_cf,
        ),
    )
    assert packaged.status == "PREVIEWED"

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
    writer = MemoryLocalCsvInventoryResultWriter()
    confirm = ConfirmLocalInventoryPackage(
        package_repo=package_repo,
        result_writer=writer,
        materializer=materializer,
        aisle_repo=aisle_repo,
        clock=clock,
        enabled=True,
        position_materializer=LocalCsvPositionMaterializer(
            position_repo=MemoryPositionRepository(),
            product_record_repo=MemoryProductRecordRepository(),
            counted_product_label_repo=MemoryInventoryCountedProductLabelRepository(),
            issued_label_resolver=IssuedProductLabelResolver(
                issued_repo=MemoryIssuedProductLabelRepository()
            ),
            inventory_repo=inventory_repo,
        ),
    )
    confirmed, duplicate = confirm.execute(
        inventory_id="inventory-1",
        export_id="export-long-cf",
        conflict_policy="SKIP",
        confirmed_by_user_id="user-1",
    )
    assert duplicate is False
    assert confirmed.status == "CONFIRMED"
    assets = asset_repo.list_by_aisle("aisle-1")
    assert len(assets) == 1
    assert len(assets[0].upload_client_file_id or "") <= SOURCE_ASSET_UPLOAD_CLIENT_FILE_ID_MAX
    assert assets[0].upload_client_file_id == fitted
    assert (assets[0].metadata_json or {}).get("upload_client_file_id_original") == long_cf


def test_preview_rejects_inventory_mismatch(tmp_path: Path) -> None:
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inv",
            status=InventoryStatus.DRAFT,
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
    preview = PreviewLocalInventoryPackage(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=package_repo,
        csv_preview=csv_preview,
        clock=clock,
        enabled=True,
        staging_root=tmp_path,
    )
    with pytest.raises(LocalInventoryPackageImportError) as exc:
        preview.execute(inventory_id="inventory-other", content=_build_zip())
    assert exc.value.code in {
        "INVENTORY_NOT_FOUND",
        "LOCAL_INVENTORY_PACKAGE_INVENTORY_MISMATCH",
    }


def _pending_csv_bytes(*, export_id: str = "export-pending-1", photo_id: str = "photo-1") -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(
        {
            "schema_version": "1",
            "export_id": export_id,
            "exported_at": "2026-08-04T10:00:00Z",
            "device_id": "device-1",
            "inventory_id": "inventory-1",
            "aisle_id": "aisle-1",
            "capture_session_id": "session-1",
            "capture_photo_id": photo_id,
            "client_file_id": "file-1",
            "capture_order": "1",
            "captured_at": "2026-08-04T09:59:00Z",
            "position_code": "",
            "internal_code": "",
            "quantity": "",
            "quantity_status": "MISSING",
            "detection_status": "stable",
            "source": "LOCAL_PENDING",
            "requires_review": "true",
            "error_code": "",
            "notes": "",
        }
    )
    return output.getvalue().encode()


def _build_pending_zip(
    *,
    export_id: str = "export-pending-1",
    photo_id: str = "photo-1",
    photo_bytes: bytes = JPEG_BYTES,
) -> bytes:
    csv_bytes = _pending_csv_bytes(export_id=export_id, photo_id=photo_id)
    file_name = f"0001_{photo_id}.jpg"
    sha = hashlib.sha256(photo_bytes).hexdigest()
    manifest = {
        "package_kind": "DINAMIC_LOCAL_AISLE_EXPORT",
        "package_version": 2,
        "status": "COMPLETE",
        "export_id": export_id,
        "inventory_id": "inventory-1",
        "aisle_id": "aisle-1",
        "capture_session_id": "session-1",
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
                "client_file_id": "file-1",
                "sequence_number": 1,
                "file_name": file_name,
                "mime_type": "image/jpeg",
                "size_bytes": len(photo_bytes),
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
        zf.writestr(f"photos/{file_name}", photo_bytes)
    return buf.getvalue()


def test_preview_rejects_local_pending_only_package(tmp_path: Path) -> None:
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
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
    preview = PreviewLocalInventoryPackage(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=package_repo,
        csv_preview=csv_preview,
        clock=clock,
        enabled=True,
        staging_root=tmp_path,
    )
    with pytest.raises(LocalInventoryPackageImportError) as exc:
        preview.execute(inventory_id="inventory-1", content=_build_pending_zip())
    assert exc.value.code == "PACKAGE_UNRESOLVED_ROWS"


def _build_multiproduct_zip(
    *,
    export_id: str = "export-multi-1",
    photo_id: str = "photo-multi-1",
    client_file_id: str = "file-multi-1",
) -> bytes:
    """One JPG, two D1 product CSV rows (same capture_photo_id)."""
    headers = HEADERS + ("label_id",)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\r\n")
    writer.writeheader()
    for sku, qty, label_id in (
        ("232424090", "1000", "6YD0S6WVMM"),
        ("232424025", "1100", "6FYR11RPXS"),
    ):
        writer.writerow(
            {
                "schema_version": "1.1",
                "export_id": export_id,
                "exported_at": "2026-08-04T10:00:00Z",
                "device_id": "device-1",
                "inventory_id": "inventory-1",
                "aisle_id": "aisle-1",
                "capture_session_id": "session-1",
                "capture_photo_id": photo_id,
                "client_file_id": client_file_id,
                "capture_order": "1",
                "captured_at": "2026-08-04T09:59:00Z",
                "position_code": "A-01",
                "internal_code": sku,
                "quantity": qty,
                "quantity_status": "PRESENT",
                "detection_status": "RESOLVED",
                "source": "LOCAL_CODE_SCAN",
                "requires_review": "false",
                "error_code": "",
                "notes": "",
                "label_id": label_id,
            }
        )
    csv_bytes = output.getvalue().encode()
    file_name = f"0001_{photo_id}.jpg"
    sha = hashlib.sha256(JPEG_BYTES).hexdigest()
    manifest = {
        "package_kind": "DINAMIC_LOCAL_AISLE_EXPORT",
        "package_version": 2,
        "status": "COMPLETE",
        "export_id": export_id,
        "inventory_id": "inventory-1",
        "aisle_id": "aisle-1",
        "capture_session_id": "session-1",
        "freeze_id": "freeze-multi-1",
        "row_count": 2,
        "expected_photo_count": 1,
        "included_photo_count": 1,
        "product_result_count": 2,
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


def test_confirm_multiproduct_same_photo_reuses_one_source_asset(tmp_path: Path) -> None:
    """Multilabel CSV: N rows / 1 photo must not hit upload idempotency unique twice."""
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
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
    preview = PreviewLocalInventoryPackage(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=package_repo,
        csv_preview=csv_preview,
        clock=clock,
        enabled=True,
        staging_root=tmp_path,
    )
    packaged = preview.execute(
        inventory_id="inventory-1", content=_build_multiproduct_zip()
    )
    assert packaged.csv_import is not None
    assert packaged.csv_import.valid_rows == 2

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
    writer = MemoryLocalCsvInventoryResultWriter()
    confirm = ConfirmLocalInventoryPackage(
        package_repo=package_repo,
        result_writer=writer,
        materializer=materializer,
        aisle_repo=aisle_repo,
        clock=clock,
        enabled=True,
        position_materializer=LocalCsvPositionMaterializer(
            position_repo=MemoryPositionRepository(),
            product_record_repo=MemoryProductRecordRepository(),
            counted_product_label_repo=MemoryInventoryCountedProductLabelRepository(),
            issued_label_resolver=IssuedProductLabelResolver(
                issued_repo=MemoryIssuedProductLabelRepository()
            ),
            inventory_repo=inventory_repo,
        ),
    )
    confirmed, duplicate = confirm.execute(
        inventory_id="inventory-1",
        export_id="export-multi-1",
        conflict_policy="SKIP",
        confirmed_by_user_id="user-1",
    )
    assert duplicate is False
    assert confirmed.status == "CONFIRMED"
    results = writer.list_for_inventory("inventory-1")
    assert len(results) == 2
    assets = asset_repo.list_by_aisle("aisle-1")
    assert len(assets) == 1
    assert {r.source_asset_id for r in results} == {assets[0].id}
    assert {r.label_id for r in results} == {"6YD0S6WVMM", "6FYR11RPXS"}
