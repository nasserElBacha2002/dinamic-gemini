"""End-to-end unit flow: Pi provisional inventory + pending aisle ZIP → preview → confirm."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from src.application.services.aisle_source_asset_materializer import AisleSourceAssetMaterializer
from src.application.services.dinamic_scanner_aisle_resolver import DinamicScannerAisleResolver
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.local_csv_position_materializer import LocalCsvPositionMaterializer
from src.application.services.local_inventory_package_parser import parse_local_inventory_package
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.application.use_cases.aisles.create_aisle import CreateAisleUseCase
from src.application.use_cases.inventories.manage_local_csv_import import PreviewLocalCsvImport
from src.application.use_cases.inventories.manage_local_inventory_package import (
    ConfirmLocalInventoryPackage,
    PreviewLocalInventoryPackage,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.dinamic_scanner_txt.constants import SCANNER_TXT_PENDING_AISLE_ID
from src.domain.local_inventory_package.scanner_metadata import LocalScannerPackageImportMetadata
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    MemoryLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
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
from tests.unit.test_local_inventory_package import (
    HEADERS,
    JPEG_BYTES,
    FixedClock,
    MemoryArtifactStorage,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
CLIENT_ID = "client-a"
INVENTORY_ID = "b2222222-2222-4222-8222-222222222222"
AISLE_CODE = "PASILLO_09"


def _seed_client_and_supplier() -> tuple[MemoryClientRepository, MemoryClientSupplierRepository]:
    clients = MemoryClientRepository()
    clients.save(
        Client(
            id=CLIENT_ID,
            name="Cliente A",
            status=ClientStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    suppliers = MemoryClientSupplierRepository()
    suppliers.save(
        ClientSupplier(
            id="supplier-a",
            client_id=CLIENT_ID,
            name="Proveedor A",
            status=ClientSupplierStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    return clients, suppliers


def _build_provisional_scanner_zip(
    *,
    export_id: str = "export-provisional-1",
    photo_id: str = "photo-prov-1",
) -> bytes:
    import csv

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(
        {
            "schema_version": "1",
            "export_id": export_id,
            "exported_at": "2026-08-04T10:00:00Z",
            "device_id": "raspberry-scanner",
            "inventory_id": INVENTORY_ID,
            "aisle_id": SCANNER_TXT_PENDING_AISLE_ID,
            "capture_session_id": "session-prov-1",
            "capture_photo_id": photo_id,
            "client_file_id": "file-prov-1",
            "capture_order": "1",
            "captured_at": "2026-08-04T09:59:00Z",
            "position_code": "A-01",
            "internal_code": "SKU-PI",
            "quantity": "3",
            "quantity_status": "PRESENT",
            "detection_status": "DETECTED",
            "source": "LOCAL_CODE_SCAN",
            "requires_review": "false",
            "error_code": "",
            "notes": "",
        }
    )
    csv_bytes = output.getvalue().encode()
    file_name = f"0001_{photo_id}.jpg"
    photo_sha = hashlib.sha256(JPEG_BYTES).hexdigest()
    manifest = {
        "package_kind": "DINAMIC_LOCAL_AISLE_EXPORT",
        "package_version": 2,
        "status": "COMPLETE",
        "export_id": export_id,
        "inventory_id": INVENTORY_ID,
        "aisle_id": SCANNER_TXT_PENDING_AISLE_ID,
        "aisle_code": AISLE_CODE,
        "client_id": CLIENT_ID,
        "client_supplier_id": "supplier-a",
        "inventory_name": "Inventario Pi local",
        "inventory_provisional": True,
        "aisle_provisional": True,
        "capture_session_id": "session-prov-1",
        "freeze_id": "freeze-prov-1",
        "row_count": 1,
        "expected_photo_count": 1,
        "included_photo_count": 1,
        "csv_checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "package_checksum_sha256": "provisional-pkg",
        "photos": [
            {
                "capture_photo_id": photo_id,
                "client_file_id": "file-prov-1",
                "sequence_number": 1,
                "file_name": file_name,
                "mime_type": "image/jpeg",
                "size_bytes": len(JPEG_BYTES),
                "sha256": photo_sha,
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


def _build_stack(tmp_path: Path) -> dict[str, object]:
    clients, supplier_repo = _seed_client_and_supplier()
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    reconciler = InventoryStatusReconciler(inventory_repo, aisle_repo, FixedClock())
    create_aisle = CreateAisleUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(),
        status_reconciler=reconciler,
    )
    aisle_resolver = DinamicScannerAisleResolver(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        create_aisle=create_aisle,
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
        client_repo=clients,
        csv_import_repo=csv_repo,
        package_repo=package_repo,
        csv_preview=csv_preview,
        clock=clock,
        enabled=True,
        staging_root=tmp_path,
    )
    storage = MemoryArtifactStorage()
    materializer = AisleSourceAssetMaterializer(
        aisle_repo=aisle_repo,
        asset_repo=MemorySourceAssetRepository(),
        artifact_storage=storage,  # type: ignore[arg-type]
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            clock=clock,
        ),
    )
    writer = MemoryLocalCsvInventoryResultWriter(
        get_import_status=lambda import_id: (
            None if (rec := csv_repo.get_by_id(import_id)) is None else rec.status
        ),
    )
    confirm = ConfirmLocalInventoryPackage(
        package_repo=package_repo,
        csv_import_repo=csv_repo,
        result_writer=writer,
        materializer=materializer,
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
        aisle_resolver=aisle_resolver,
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
    return {
        "preview": preview,
        "confirm": confirm,
        "inventory_repo": inventory_repo,
        "aisle_repo": aisle_repo,
        "writer": writer,
        "supplier_repo": supplier_repo,
    }


def test_provisional_zip_parses_manifest_flags() -> None:
    parsed = parse_local_inventory_package(_build_provisional_scanner_zip())
    assert parsed.inventory_id == INVENTORY_ID
    assert parsed.manifest.get("inventory_provisional") is True
    assert parsed.manifest.get("aisle_provisional") is True
    assert parsed.manifest.get("aisle_code") == AISLE_CODE


def test_preview_creates_inventory_and_pending_aisle_binding(tmp_path: Path) -> None:
    stack = _build_stack(tmp_path)
    preview = stack["preview"]
    inventory_repo = stack["inventory_repo"]
    aisle_repo = stack["aisle_repo"]
    assert isinstance(preview, PreviewLocalInventoryPackage)
    assert isinstance(inventory_repo, MemoryInventoryRepository)
    assert inventory_repo.get_by_id(INVENTORY_ID) is None
    assert isinstance(aisle_repo, MemoryAisleRepository)
    assert not aisle_repo.list_by_inventory(INVENTORY_ID)

    packaged = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_build_provisional_scanner_zip(),
    )

    inv = inventory_repo.get_by_id(INVENTORY_ID)
    assert inv is not None
    assert inv.client_id == CLIENT_ID
    assert inv.name == "Inventario Pi local"
    assert packaged.status == "PREVIEWED"
    assert packaged.aisle_id == SCANNER_TXT_PENDING_AISLE_ID
    assert packaged.csv_import is not None
    assert packaged.csv_import.rows[0].aisle_id == SCANNER_TXT_PENDING_AISLE_ID
    metadata = LocalScannerPackageImportMetadata.from_json(
        packaged.csv_import.source_metadata_json
    )
    assert metadata is not None
    assert metadata.aisle_will_be_created is True
    assert metadata.aisle_code == AISLE_CODE
    assert metadata.client_supplier_id == "supplier-a"
    assert metadata.inventory_provisional is True


def test_confirm_materializes_aisle_and_replaces_pending_rows(tmp_path: Path) -> None:
    stack = _build_stack(tmp_path)
    preview = stack["preview"]
    confirm = stack["confirm"]
    aisle_repo = stack["aisle_repo"]
    writer = stack["writer"]
    assert isinstance(preview, PreviewLocalInventoryPackage)
    assert isinstance(confirm, ConfirmLocalInventoryPackage)
    assert isinstance(aisle_repo, MemoryAisleRepository)
    assert isinstance(writer, MemoryLocalCsvInventoryResultWriter)

    preview.execute(inventory_id=INVENTORY_ID, content=_build_provisional_scanner_zip())
    confirmed, duplicate = confirm.execute(
        inventory_id=INVENTORY_ID,
        export_id="export-provisional-1",
        conflict_policy="SKIP",
        confirmed_by_user_id="user-test",
    )
    assert duplicate is False
    assert confirmed.status == "CONFIRMED"
    aisles = aisle_repo.list_by_inventory(INVENTORY_ID)
    assert len(aisles) == 1
    assert aisles[0].code == AISLE_CODE
    assert confirmed.aisle_id == aisles[0].id
    assert confirmed.csv_import is not None
    assert all(row.aisle_id == aisles[0].id for row in confirmed.csv_import.rows)
    assert len(writer.list_for_inventory(INVENTORY_ID)) >= 1
    metadata = LocalScannerPackageImportMetadata.from_json(
        confirmed.csv_import.source_metadata_json
    )
    assert metadata is not None
    assert metadata.aisle_created_on_confirm is True


def test_confirm_uses_manifest_supplier_when_multiple_suppliers(tmp_path: Path) -> None:
    stack = _build_stack(tmp_path)
    supplier_repo = stack["supplier_repo"]
    assert isinstance(supplier_repo, MemoryClientSupplierRepository)
    supplier_repo.save(
        ClientSupplier(
            id="supplier-b",
            client_id=CLIENT_ID,
            name="Proveedor B",
            status=ClientSupplierStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    preview = stack["preview"]
    confirm = stack["confirm"]
    aisle_repo = stack["aisle_repo"]
    assert isinstance(preview, PreviewLocalInventoryPackage)
    assert isinstance(confirm, ConfirmLocalInventoryPackage)
    assert isinstance(aisle_repo, MemoryAisleRepository)

    preview.execute(inventory_id=INVENTORY_ID, content=_build_provisional_scanner_zip())
    confirmed, duplicate = confirm.execute(
        inventory_id=INVENTORY_ID,
        export_id="export-provisional-1",
        conflict_policy="SKIP",
        confirmed_by_user_id="user-test",
    )
    assert duplicate is False
    aisle = aisle_repo.get_by_inventory_and_code(INVENTORY_ID, AISLE_CODE)
    assert aisle is not None
    assert aisle.client_supplier_id == "supplier-a"
    assert confirmed.aisle_id == aisle.id
