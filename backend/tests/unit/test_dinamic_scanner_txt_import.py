from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.services.dinamic_scanner_aisle_resolver import DinamicScannerAisleResolver
from src.application.services.dinamic_scanner_txt_parser import parse_dinamic_scanner_txt
from src.application.services.dinamic_scanner_txt_to_local_csv import (
    build_parsed_local_csv_from_scanner_txt,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.local_csv_position_materializer import LocalCsvPositionMaterializer
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.application.use_cases.aisles.create_aisle import CreateAisleUseCase
from src.application.use_cases.inventories.manage_dinamic_scanner_txt_import import (
    ConfirmDinamicScannerTxtImport,
    PreviewDinamicScannerTxtImport,
)
from src.application.use_cases.inventories.manage_local_csv_import import (
    ConfirmLocalCsvImport,
    PreviewLocalCsvImport,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.dinamic_scanner_txt.constants import SCANNER_TXT_PENDING_AISLE_ID
from src.domain.dinamic_scanner_txt.errors import (
    TXT_SUPPLIER_AMBIGUOUS,
    DinamicScannerTxtImportError,
)
from src.domain.dinamic_scanner_txt.metadata import DinamicScannerTxtImportMetadata
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.local_csv_import.sources import (
    INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
    INGESTION_SOURCE_LOCAL_CSV_IMPORT,
)
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
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


class FixedClock:
    def now(self) -> datetime:
        return NOW


def _txt(*lines: str) -> bytes:
    return "\n".join(lines).encode()


def _seed_inventory_with_client(
    *,
    supplier_count: int = 1,
) -> tuple[
    MemoryInventoryRepository,
    MemoryAisleRepository,
    MemoryClientSupplierRepository,
    str,
    list[str],
]:
    client_repo = MemoryClientRepository()
    client_id = "client-1"
    client_repo.save(
        Client(
            id=client_id,
            name="Client",
            status=ClientStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    inventory_repo = MemoryInventoryRepository()
    inventory_id = "inventory-1"
    inventory_repo.save(
        Inventory(
            id=inventory_id,
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
            client_id=client_id,
        )
    )
    supplier_repo = MemoryClientSupplierRepository()
    supplier_ids: list[str] = []
    for index in range(supplier_count):
        sid = f"supplier-{index + 1}"
        supplier_repo.save(
            ClientSupplier(
                id=sid,
                client_id=client_id,
                name=f"Supplier {index + 1}",
                status=ClientSupplierStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        supplier_ids.append(sid)
    aisle_repo = MemoryAisleRepository()
    return inventory_repo, aisle_repo, supplier_repo, inventory_id, supplier_ids


def _build_preview_confirm(
    inventory_repo: MemoryInventoryRepository,
    aisle_repo: MemoryAisleRepository,
    supplier_repo: MemoryClientSupplierRepository,
) -> tuple[
    PreviewDinamicScannerTxtImport,
    ConfirmDinamicScannerTxtImport,
    MemoryLocalCsvImportRepository,
    MemoryLocalCsvInventoryResultWriter,
]:
    import_repo = MemoryLocalCsvImportRepository()
    csv_preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    reconciler = InventoryStatusReconciler(inventory_repo, aisle_repo, FixedClock())
    create_aisle = CreateAisleUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(),
        status_reconciler=reconciler,
    )
    resolver = DinamicScannerAisleResolver(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        create_aisle=create_aisle,
    )
    writer = MemoryLocalCsvInventoryResultWriter()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    confirm_csv = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=writer,
        clock=FixedClock(),
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
        aisle_repo=aisle_repo,
    )
    preview = PreviewDinamicScannerTxtImport(
        inventory_repo=inventory_repo,
        aisle_resolver=resolver,
        import_repo=import_repo,
        csv_preview=csv_preview,
        clock=FixedClock(),
        enabled=True,
        max_lines=10_000,
        max_line_length=512,
    )
    confirm = ConfirmDinamicScannerTxtImport(
        import_repo=import_repo,
        aisle_resolver=resolver,
        csv_confirm=confirm_csv,
        enabled=True,
    )
    return preview, confirm, import_repo, writer, position_repo, product_repo


def test_preview_does_not_materialize_productive_rows() -> None:
    """Phase 4: preview must not create ProductRecord, Position, or productive writer rows."""
    inventory_repo, aisle_repo, supplier_repo, inventory_id, _ = _seed_inventory_with_client()
    preview, _, _, writer, position_repo, product_repo = _build_preview_confirm(
        inventory_repo, aisle_repo, supplier_repo
    )
    preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        ),
        filename="Pasillo_A_04.txt",
    )
    assert writer.list_for_inventory(inventory_id) == ()
    assert not position_repo._store  # noqa: SLF001 — preview purity snapshot
    assert not product_repo._store  # noqa: SLF001


def test_preview_does_not_create_aisle() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, _ = _seed_inventory_with_client()
    preview, _, _, _, _, _ = _build_preview_confirm(inventory_repo, aisle_repo, supplier_repo)

    result = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        ),
        filename="Pasillo_A_04.txt",
    )

    assert result.aisle_created is False
    assert result.aisle_will_be_created is True
    assert result.aisle_id == ""
    assert len(aisle_repo.list_by_inventory(inventory_id)) == 0
    assert result.csv_import.rows[0].aisle_id == SCANNER_TXT_PENDING_AISLE_ID
    metadata = DinamicScannerTxtImportMetadata.from_json(result.csv_import.source_metadata_json)
    assert metadata is not None
    assert metadata.aisle_code == "Pasillo_A_04"
    assert metadata.aisle_will_be_created is True


def test_preview_reuses_existing_aisle_without_creating() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, supplier_ids = _seed_inventory_with_client()
    aisle_repo.save(
        Aisle(
            id="aisle-existing",
            inventory_id=inventory_id,
            code="Pasillo_A_04",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
            client_supplier_id=supplier_ids[0],
        )
    )
    preview, _, _, _, _, _ = _build_preview_confirm(inventory_repo, aisle_repo, supplier_repo)

    result = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        ),
        filename="Pasillo_A_04.txt",
    )

    assert result.aisle_will_be_created is False
    assert result.aisle_id == "aisle-existing"
    assert len(aisle_repo.list_by_inventory(inventory_id)) == 1


def test_confirm_creates_aisle_and_preserves_metadata() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, _ = _seed_inventory_with_client()
    preview, confirm, _, _, _, _ = _build_preview_confirm(inventory_repo, aisle_repo, supplier_repo)
    staged = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        ),
        filename="Pasillo_A_04.txt",
    )

    confirmed = confirm.execute(
        inventory_id=inventory_id,
        export_id=staged.csv_import.export_id,
    )

    assert confirmed.aisle_created is True
    assert confirmed.aisle_code == "Pasillo_A_04"
    assert confirmed.parse_warnings == staged.parse_warnings
    assert confirmed.positions_imported == staged.positions_imported
    aisle = aisle_repo.get_by_inventory_and_code(inventory_id, "Pasillo_A_04")
    assert aisle is not None
    assert confirmed.csv_import.rows[0].aisle_id == aisle.id


def test_confirm_is_idempotent_on_duplicate_export() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, _ = _seed_inventory_with_client()
    preview, confirm, _, _, _, _ = _build_preview_confirm(inventory_repo, aisle_repo, supplier_repo)
    staged = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        ),
        filename="Pasillo_A_04.txt",
    )
    first = confirm.execute(inventory_id=inventory_id, export_id=staged.csv_import.export_id)
    second = confirm.execute(inventory_id=inventory_id, export_id=staged.csv_import.export_id)
    assert first.duplicate is False
    assert second.duplicate is True
    assert len(aisle_repo.list_by_inventory(inventory_id)) == 1


def test_supplier_ambiguous_on_confirm_when_multiple_suppliers() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, _ = _seed_inventory_with_client(
        supplier_count=2
    )
    preview, confirm, _, _, _, _ = _build_preview_confirm(inventory_repo, aisle_repo, supplier_repo)
    staged = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        ),
        filename="New_Aisle.txt",
    )
    with pytest.raises(DinamicScannerTxtImportError) as exc:
        confirm.execute(
            inventory_id=inventory_id,
            export_id=staged.csv_import.export_id,
        )
    assert exc.value.code == TXT_SUPPLIER_AMBIGUOUS


def test_duplicate_label_id_in_file_is_rejected_on_preview() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, supplier_ids = _seed_inventory_with_client()
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id=inventory_id,
            code="Aisle",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
            client_supplier_id=supplier_ids[0],
        )
    )
    preview, _, _, _, _, _ = _build_preview_confirm(inventory_repo, aisle_repo, supplier_repo)
    result = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
            "D1|A1B2C3D4E5|SKU002|50|E",
        ),
        filename="Aisle.txt",
    )
    rejected = [row for row in result.csv_import.rows if row.status == "REJECTED"]
    assert len(rejected) == 1
    assert "secondary_key:duplicate_in_file" in rejected[0].validation_errors


def test_confirm_applies_txt_results_without_image() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, supplier_ids = _seed_inventory_with_client()
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id=inventory_id,
            code="Pasillo_A_04",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
            client_supplier_id=supplier_ids[0],
        )
    )
    preview, confirm, _, writer, _, _ = _build_preview_confirm(inventory_repo, aisle_repo, supplier_repo)
    staged = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        ),
        filename="Pasillo_A_04.txt",
    )
    confirmed = confirm.execute(
        inventory_id=inventory_id,
        export_id=staged.csv_import.export_id,
    )
    results = writer.list_for_inventory(inventory_id)
    assert len(results) == 1
    assert results[0].has_image_evidence is False
    assert results[0].ingestion_source == INGESTION_SOURCE_DINAMIC_SCANNER_TXT
    assert confirmed.csv_import.valid_rows == 1


def test_zip_csv_ingestion_source_regression() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, supplier_ids = _seed_inventory_with_client()
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id=inventory_id,
            code="A",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
            client_supplier_id=supplier_ids[0],
        )
    )
    import_repo = MemoryLocalCsvImportRepository()
    from src.application.use_cases.inventories.manage_local_csv_import import PreviewLocalCsvImport
    from tests.unit.test_local_csv_import import _csv_bytes

    preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    record = preview.execute(inventory_id=inventory_id, content=_csv_bytes())
    assert record.rows[0].ingestion_source == INGESTION_SOURCE_LOCAL_CSV_IMPORT


def test_converter_maps_position_and_quantity() -> None:
    parsed_txt = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        )
    )
    parsed_csv = build_parsed_local_csv_from_scanner_txt(
        parsed_txt=parsed_txt,
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        aisle_code="Pasillo_A_04",
        exported_at=NOW,
    )
    row = parsed_csv.rows[0]
    assert row.values["position_code"] == "04"
    assert row.values["position_label_id"] == "POS001"
    assert row.quantity == 100
    assert "position_payload_raw" in row.values
    assert row.values["position_payload_raw"]
    assert row.values["capture_photo_id"].startswith("txt-scan-")
