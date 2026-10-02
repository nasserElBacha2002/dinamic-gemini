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
    writer = MemoryLocalCsvInventoryResultWriter(
        get_import_status=lambda import_id: (
            None
            if (rec := import_repo.get_by_id(import_id)) is None
            else rec.status
        ),
    )
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    confirm_csv = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=writer,
        clock=FixedClock(),
        enabled=True,
        inventory_repo=inventory_repo,
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


def test_confirm_uses_explicit_supplier_when_multiple_suppliers() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, supplier_ids = (
        _seed_inventory_with_client(supplier_count=2)
    )
    preview, confirm, _, _, _, _ = _build_preview_confirm(
        inventory_repo, aisle_repo, supplier_repo
    )
    staged = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        ),
        filename="P1.txt",
    )

    confirmed = confirm.execute(
        inventory_id=inventory_id,
        export_id=staged.csv_import.export_id,
        client_supplier_id=supplier_ids[1],
    )

    aisle = aisle_repo.get_by_inventory_and_code(inventory_id, "P1")
    assert confirmed.aisle_created is True
    assert aisle is not None
    assert aisle.client_supplier_id == supplier_ids[1]


def test_confirm_rejects_explicit_supplier_from_another_client() -> None:
    inventory_repo, aisle_repo, supplier_repo, inventory_id, _ = _seed_inventory_with_client(
        supplier_count=2
    )
    supplier_repo.save(
        ClientSupplier(
            id="foreign-supplier",
            client_id="another-client",
            name="Foreign",
            status=ClientSupplierStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    preview, confirm, _, _, _, _ = _build_preview_confirm(
        inventory_repo, aisle_repo, supplier_repo
    )
    staged = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            "D1|A1B2C3D4E5|SKU001|100|E",
        ),
        filename="P1.txt",
    )

    with pytest.raises(DinamicScannerTxtImportError) as exc:
        confirm.execute(
            inventory_id=inventory_id,
            export_id=staged.csv_import.export_id,
            client_supplier_id="foreign-supplier",
        )

    assert exc.value.code == "DINAMIC_SCANNER_TXT_CLIENT_SUPPLIER_MISMATCH"
    assert aisle_repo.get_by_inventory_and_code(inventory_id, "P1") is None


def test_duplicate_label_id_in_file_is_omitted_once() -> None:
    """Unique instance label_id repeats keep a single product within the TXT scope."""
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
    from src.domain.product_labels.format import build_product_label_payload

    line = build_product_label_payload(
        label_id="A1B2C3D4E5", internal_code="SKU001", quantity=100
    )
    result = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            line,
            line,
        ),
        filename="Aisle.txt",
    )
    assert result.products_imported == 1
    assert len(result.csv_import.rows) == 1
    assert any("duplicate_unique_label_id" in w for w in result.parse_warnings)


def test_pipe_item_without_supplier_does_not_bypass_validation() -> None:
    """identifier|quantity requires resolvable supplier/profile — no silent accept."""
    inventory_repo = MemoryInventoryRepository()
    inventory_id = "inv-no-supplier"
    inventory_repo.save(
        Inventory(
            id=inventory_id,
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
            client_id="client-1",
        )
    )
    supplier_repo = MemoryClientSupplierRepository()
    aisle_repo = MemoryAisleRepository()
    preview, _, _, _, _, _ = _build_preview_confirm(inventory_repo, aisle_repo, supplier_repo)
    with pytest.raises(DinamicScannerTxtImportError) as exc:
        preview.execute(
            inventory_id=inventory_id,
            content=_txt("ASI-DDWDD8|48"),
            filename="Pasillo_Raw.txt",
        )
    assert exc.value.code == "DINAMIC_SCANNER_TXT_CLIENT_SUPPLIER_REQUIRED"


def test_preview_raspberry_pipe_items_without_position_end_to_end() -> None:
    """Real Raspberry TXT (no POSITION) through PreviewDinamicScannerTxtImport + ITEM profile."""
    from dataclasses import replace

    from src.application.services.label_profile_resolver import LabelProfileResolver
    from src.domain.client_supplier.extraction_profile import (
        CharacterSetPolicy,
        DeterministicBarcodeRules,
        ExtractionProfileStatus,
        FieldMappingRule,
        FieldMappingSource,
        ItemLabelSemanticType,
        QuantityExtractionRules,
        QuantityPresence,
        RecognitionMode,
        SupplierExtractionProfile,
        minimal_supplier_item_configuration,
    )
    from src.domain.label_profiles.entities import ClientSupplierLabelProfile
    from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
    from src.domain.local_csv_import.statuses import LOCAL_CSV_IMPORT_STATUS_PREVIEWED
    from src.infrastructure.repositories.memory_client_supplier_label_profile_repository import (
        MemoryClientSupplierLabelProfileRepository,
    )
    from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
        MemorySupplierExtractionProfileRepository,
    )

    inventory_repo, aisle_repo, supplier_repo, inventory_id, supplier_ids = (
        _seed_inventory_with_client()
    )
    supplier_id = supplier_ids[0]
    aisle_repo.save(
        Aisle(
            id="aisle-raw",
            inventory_id=inventory_id,
            code="Pasillo_Raw",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
            client_supplier_id=supplier_id,
        )
    )

    item_cfg = replace(
        minimal_supplier_item_configuration(
            expected_prefix="ASI-",
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
        ),
        recognition_mode=RecognitionMode.FULL,
        required_fields=("sku",),
        semantic_type=ItemLabelSemanticType.PRODUCT_SKU.value,
        quantity_rules=QuantityExtractionRules(
            required=False,
            minimum=1,
            expected_presence=QuantityPresence.OPTIONAL,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="ASI-",
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
            field_mappings=(FieldMappingRule("sku", FieldMappingSource.WHOLE, None),),
        ),
    )
    extraction_repo = MemorySupplierExtractionProfileRepository()
    extraction_repo.save(
        SupplierExtractionProfile(
            id="ext-item-asi",
            client_id="client-1",
            supplier_id=supplier_id,
            profile_key="default",
            version=1,
            status=ExtractionProfileStatus.ACTIVE,
            configuration=item_cfg,
            visual_notes=None,
            created_by=None,
            created_at=NOW,
            updated_at=NOW,
            label_kind=LabelKind.ITEM,
        )
    )
    label_profiles = MemoryClientSupplierLabelProfileRepository()
    label_profiles.upsert(
        ClientSupplierLabelProfile(
            id="cfg-item",
            client_supplier_id=supplier_id,
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    resolver = LabelProfileResolver(
        label_profile_repo=label_profiles,
        client_supplier_repo=supplier_repo,
        extraction_profile_repo=extraction_repo,
    )

    import_repo = MemoryLocalCsvImportRepository()
    csv_preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    create_aisle = CreateAisleUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(),
        status_reconciler=InventoryStatusReconciler(
            inventory_repo, aisle_repo, FixedClock()
        ),
    )
    aisle_resolver = DinamicScannerAisleResolver(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        create_aisle=create_aisle,
    )
    preview = PreviewDinamicScannerTxtImport(
        inventory_repo=inventory_repo,
        aisle_resolver=aisle_resolver,
        import_repo=import_repo,
        csv_preview=csv_preview,
        clock=FixedClock(),
        enabled=True,
        max_lines=10_000,
        max_line_length=512,
        label_profile_resolver=resolver,
        extraction_profile_repo=extraction_repo,
    )

    result = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "ASI-DDWDD8|48",
            "ASI-LDFMEE|10",
            "ASI-U59KNU|8",
        ),
        filename="Pasillo_Raw.txt",
    )

    assert result.products_imported == 3
    assert result.positions_imported == 0
    assert len(result.csv_import.rows) == 3
    assert result.csv_import.status == LOCAL_CSV_IMPORT_STATUS_PREVIEWED
    codes = [row.internal_code for row in result.csv_import.rows]
    qtys = [row.quantity for row in result.csv_import.rows]
    assert codes == ["ASI-DDWDD8", "ASI-LDFMEE", "ASI-U59KNU"]
    assert qtys == [48, 10, 8]
    assert all(not (row.label_id or "").strip() for row in result.csv_import.rows)
    assert all(row.requires_review is True for row in result.csv_import.rows)
    assert all(row.status != "REJECTED" for row in result.csv_import.rows)
    assert all(not (row.position_code or "").strip() for row in result.csv_import.rows)


def test_preview_raspberry_pipe_items_without_preexisting_aisle() -> None:
    """Raspberry TXT without preexisting aisle: sole supplier + pending aisle staging."""
    from dataclasses import replace

    from src.application.services.label_profile_resolver import LabelProfileResolver
    from src.domain.client_supplier.extraction_profile import (
        CharacterSetPolicy,
        DeterministicBarcodeRules,
        ExtractionProfileStatus,
        FieldMappingRule,
        FieldMappingSource,
        ItemLabelSemanticType,
        QuantityExtractionRules,
        QuantityPresence,
        RecognitionMode,
        SupplierExtractionProfile,
        minimal_supplier_item_configuration,
    )
    from src.domain.label_profiles.entities import ClientSupplierLabelProfile
    from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
    from src.domain.local_csv_import.statuses import LOCAL_CSV_IMPORT_STATUS_PREVIEWED
    from src.infrastructure.repositories.memory_client_supplier_label_profile_repository import (
        MemoryClientSupplierLabelProfileRepository,
    )
    from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
        MemorySupplierExtractionProfileRepository,
    )

    inventory_repo, aisle_repo, supplier_repo, inventory_id, supplier_ids = (
        _seed_inventory_with_client()
    )
    supplier_id = supplier_ids[0]
    assert len(aisle_repo.list_by_inventory(inventory_id)) == 0

    item_cfg = replace(
        minimal_supplier_item_configuration(
            expected_prefix="ASI-",
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
        ),
        recognition_mode=RecognitionMode.FULL,
        required_fields=("sku",),
        semantic_type=ItemLabelSemanticType.PRODUCT_SKU.value,
        quantity_rules=QuantityExtractionRules(
            required=False,
            minimum=1,
            expected_presence=QuantityPresence.OPTIONAL,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="ASI-",
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
            field_mappings=(FieldMappingRule("sku", FieldMappingSource.WHOLE, None),),
        ),
    )
    extraction_repo = MemorySupplierExtractionProfileRepository()
    extraction_repo.save(
        SupplierExtractionProfile(
            id="ext-item-asi-pending",
            client_id="client-1",
            supplier_id=supplier_id,
            profile_key="default",
            version=1,
            status=ExtractionProfileStatus.ACTIVE,
            configuration=item_cfg,
            visual_notes=None,
            created_by=None,
            created_at=NOW,
            updated_at=NOW,
            label_kind=LabelKind.ITEM,
        )
    )
    label_profiles = MemoryClientSupplierLabelProfileRepository()
    label_profiles.upsert(
        ClientSupplierLabelProfile(
            id="cfg-item-pending",
            client_supplier_id=supplier_id,
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    resolver = LabelProfileResolver(
        label_profile_repo=label_profiles,
        client_supplier_repo=supplier_repo,
        extraction_profile_repo=extraction_repo,
    )

    import_repo = MemoryLocalCsvImportRepository()
    csv_preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    create_aisle = CreateAisleUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(),
        status_reconciler=InventoryStatusReconciler(
            inventory_repo, aisle_repo, FixedClock()
        ),
    )
    aisle_resolver = DinamicScannerAisleResolver(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        create_aisle=create_aisle,
    )
    preview = PreviewDinamicScannerTxtImport(
        inventory_repo=inventory_repo,
        aisle_resolver=aisle_resolver,
        import_repo=import_repo,
        csv_preview=csv_preview,
        clock=FixedClock(),
        enabled=True,
        max_lines=10_000,
        max_line_length=512,
        label_profile_resolver=resolver,
        extraction_profile_repo=extraction_repo,
    )

    result = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "ASI-DDWDD8|48",
            "ASI-LDFMEE|10",
            "ASI-U59KNU|8",
        ),
        filename="Pasillo_Raw.txt",
    )

    assert result.aisle_will_be_created is True
    assert result.aisle_created is False
    assert result.aisle_id == ""
    assert len(aisle_repo.list_by_inventory(inventory_id)) == 0
    assert result.products_imported == 3
    assert result.positions_imported == 0
    assert result.csv_import.status == LOCAL_CSV_IMPORT_STATUS_PREVIEWED
    assert len(result.csv_import.rows) == 3
    assert all(row.aisle_id == SCANNER_TXT_PENDING_AISLE_ID for row in result.csv_import.rows)
    codes = [row.internal_code for row in result.csv_import.rows]
    qtys = [row.quantity for row in result.csv_import.rows]
    assert codes == ["ASI-DDWDD8", "ASI-LDFMEE", "ASI-U59KNU"]
    assert qtys == [48, 10, 8]
    assert all(not (row.label_id or "").strip() for row in result.csv_import.rows)
    assert all(row.requires_review is True for row in result.csv_import.rows)
    assert all(row.status != "REJECTED" for row in result.csv_import.rows)
    assert all(not (row.position_code or "").strip() for row in result.csv_import.rows)
    metadata = DinamicScannerTxtImportMetadata.from_json(result.csv_import.source_metadata_json)
    assert metadata is not None
    assert metadata.aisle_code == "Pasillo_Raw"
    assert metadata.aisle_will_be_created is True


def test_preview_invalid_d1_then_valid_same_label_id_keeps_good_importable() -> None:
    """BAD D1 + GOOD D1 same LABEL_ID: invalid must not claim secondary_key identity."""
    import json
    from pathlib import Path

    from src.domain.local_csv_import.statuses import LOCAL_CSV_IMPORT_STATUS_PREVIEWED
    from src.domain.product_labels.format import build_product_label_payload

    vectors_path = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "product-labels"
        / "v1"
        / "checksum-vectors.json"
    )
    vectors = json.loads(vectors_path.read_text(encoding="utf-8"))
    bad = next(
        v["tampered_payload"]
        for v in vectors["vectors"]
        if v["name"] == "checksum-fail-tampered-qty"
    )
    label_id = bad.split("|")[1]
    good = build_product_label_payload(
        label_id=label_id, internal_code="SKU001", quantity=100
    )

    inventory_repo, aisle_repo, supplier_repo, inventory_id, supplier_ids = (
        _seed_inventory_with_client()
    )
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
    preview, _, _, _, _, _ = _build_preview_confirm(inventory_repo, aisle_repo, supplier_repo)
    result = preview.execute(
        inventory_id=inventory_id,
        content=_txt(
            "POSITION|POS001|04|RIGHT",
            bad,
            good,
        ),
        filename="Pasillo_A_04.txt",
    )

    assert result.csv_import.status == LOCAL_CSV_IMPORT_STATUS_PREVIEWED
    assert len(result.csv_import.rows) == 2
    bad_row, good_row = result.csv_import.rows
    assert "d1:checksum_failed" in bad_row.validation_errors
    assert bad_row.status == "REJECTED"
    # Invalid D1 must not claim label_id, but notes keep observed id for audit.
    assert not (bad_row.label_id or "").strip()
    assert f"OBSERVED_LABEL_ID={label_id.upper()}" in (bad_row.notes or "").upper()
    assert "secondary_key:duplicate_in_file" not in good_row.validation_errors
    assert good_row.status != "REJECTED"
    assert (good_row.label_id or "").upper() == label_id.upper()
    assert result.products_imported == 1


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
