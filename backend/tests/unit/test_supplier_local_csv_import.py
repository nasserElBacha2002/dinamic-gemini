"""Supplier-aware legacy local CSV import — regression + golden pruebas b fixtures."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

import pytest

from src.application.services.local_csv_parser import parse_local_csv
from src.application.services.local_csv_supplier_import_metadata import (
    parse_supplier_import_notes,
)
from src.application.services.local_inventory_package_row_gate import (
    assert_package_csv_rows_ready,
)
from src.application.services.supplier_extraction_profiles.pruebas_b_segmented_configurations import (
    pruebas_b_item_segmented_configuration,
    pruebas_b_position_segmented_configuration,
)
from src.application.services.supplier_local_csv_row_revalidator import (
    build_supplier_local_csv_row_revalidator,
)
from src.application.use_cases.inventories.manage_local_csv_import import (
    ConfirmLocalCsvImport,
    PreviewLocalCsvImport,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    SupplierExtractionProfile,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.label_profiles.kinds import LabelKind
from src.domain.product_labels.format import generate_product_label_id
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    MemoryLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_local_csv_import_repository import (
    MemoryLocalCsvImportRepository,
)
from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
    MemorySupplierExtractionProfileRepository,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
CLIENT_ID = "client-1"
INVENTORY_ID = "inventory-1"
AISLE_ID = "aisle-1"
SUPPLIER_ID = "c314c8c3-b6fd-490c-98dc-7b1ac40dca47"
ITEM_PROFILE_ID = "prof-item-v10"
POS_PROFILE_ID = "prof-pos-v3"

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
    "label_id",
    "position_label_id",
    "position_payload_raw",
)


class FixedClock:
    def now(self) -> datetime:
        return NOW


def _supplier_notes(
    *,
    label_kind: str,
    raw_payload: str,
    profile_id: str,
    profile_version: int,
    client_supplier_id: str = SUPPLIER_ID,
) -> str:
    return json.dumps(
        {
            "supplier_import": {
                "client_supplier_id": client_supplier_id,
                "label_kind": label_kind,
                "profile_id": profile_id,
                "profile_version": profile_version,
                "raw_payload": raw_payload,
            }
        },
        separators=(",", ":"),
    )


def _csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS, lineterminator="\r\n")
    writer.writeheader()
    base = {
        "schema_version": "1.1",
        "export_id": "export-golden",
        "exported_at": "2026-09-01T10:00:00+00:00",
        "device_id": "device-1",
        "inventory_id": INVENTORY_ID,
        "aisle_id": AISLE_ID,
        "capture_session_id": "session-1",
        "capture_photo_id": "photo-base",
        "client_file_id": "file-base",
        "capture_order": "1",
        "captured_at": "2026-09-01T09:59:00+00:00",
        "position_code": "A04-R-02",
        "internal_code": "",
        "quantity": "",
        "quantity_status": "PRESENT",
        "detection_status": "DETECTED",
        "source": "LOCAL_CODE_SCAN",
        "requires_review": "false",
        "error_code": "",
        "notes": "",
        "label_id": "",
        "position_label_id": "",
        "position_payload_raw": "",
    }
    for idx, row in enumerate(rows, start=1):
        merged = {**base, **row}
        if "capture_photo_id" not in row:
            merged["capture_photo_id"] = f"photo-{idx}"
        if "client_file_id" not in row:
            merged["client_file_id"] = f"file-{idx}"
        if "capture_order" not in row:
            merged["capture_order"] = str(idx)
        writer.writerow(merged)
    return output.getvalue().encode()


def _seed_profiles(
    repo: MemorySupplierExtractionProfileRepository,
    *,
    item_version: int = 10,
    position_version: int = 3,
    include_item_v10: bool = True,
    include_item_v11: bool = False,
    item_supplier_id: str = SUPPLIER_ID,
) -> None:
    if include_item_v10:
        repo.save(
            SupplierExtractionProfile(
                id=ITEM_PROFILE_ID,
                client_id=CLIENT_ID,
                supplier_id=item_supplier_id,
                profile_key="ITEM",
                version=item_version,
                status=(
                    ExtractionProfileStatus.SUPERSEDED
                    if include_item_v11
                    else ExtractionProfileStatus.ACTIVE
                ),
                configuration=pruebas_b_item_segmented_configuration(),
                visual_notes=None,
                created_by=None,
                created_at=NOW,
                label_kind=LabelKind.ITEM,
            )
        )
    if include_item_v11:
        repo.save(
            SupplierExtractionProfile(
                id="prof-item-v11",
                client_id=CLIENT_ID,
                supplier_id=item_supplier_id,
                profile_key="ITEM",
                version=11,
                status=ExtractionProfileStatus.ACTIVE,
                configuration=pruebas_b_item_segmented_configuration(),
                visual_notes=None,
                created_by=None,
                created_at=NOW,
                label_kind=LabelKind.ITEM,
            )
        )
    repo.save(
        SupplierExtractionProfile(
            id=POS_PROFILE_ID,
            client_id=CLIENT_ID,
            supplier_id=item_supplier_id,
            profile_key="POSITION",
            version=position_version,
            status=ExtractionProfileStatus.ACTIVE,
            configuration=pruebas_b_position_segmented_configuration(),
            visual_notes=None,
            created_by=None,
            created_at=NOW,
            label_kind=LabelKind.POSITION,
        )
    )


def _preview_stack(
    *,
    profiles: MemorySupplierExtractionProfileRepository | None = None,
) -> tuple[PreviewLocalCsvImport, MemoryLocalCsvImportRepository, MemoryInventoryRepository, MemoryAisleRepository]:
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id=INVENTORY_ID,
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
            client_id=CLIENT_ID,
        )
    )
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(
        Aisle(
            id=AISLE_ID,
            inventory_id=INVENTORY_ID,
            code="A04",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
            client_supplier_id=SUPPLIER_ID,
        )
    )
    supplier_repo = MemoryClientSupplierRepository()
    supplier_repo.save(
        ClientSupplier(
            id=SUPPLIER_ID,
            client_id=CLIENT_ID,
            name="pruebas b",
            status=ClientSupplierStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    profile_repo = profiles or MemorySupplierExtractionProfileRepository()
    if profiles is None:
        _seed_profiles(profile_repo)
    import_repo = MemoryLocalCsvImportRepository()
    preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
        supplier_revalidator=build_supplier_local_csv_row_revalidator(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            client_supplier_repo=supplier_repo,
            extraction_profile_repo=profile_repo,
        ),
    )
    return preview, import_repo, inventory_repo, aisle_repo


def test_metadata_parser_requires_explicit_fields() -> None:
    result = parse_supplier_import_notes(
        json.dumps({"supplier_import": {"profile_id": "p1"}})
    )
    assert result.supplier_import_present is True
    assert result.metadata is None
    assert "supplier_import:missing_client_supplier_id" in result.errors


def test_parser_skips_d1_for_supplier_row() -> None:
    parsed = parse_local_csv(
        _csv_bytes(
            {
                "capture_photo_id": "photo-item",
                "internal_code": "SKU773421",
                "label_id": "LPNA000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="ITEM",
                    raw_payload="LPNA000184|SKU773421|24",
                    profile_id=ITEM_PROFILE_ID,
                    profile_version=10,
                ),
            }
        )
    )
    row = parsed.rows[0]
    assert "label_id:invalid_format" not in row.errors
    assert row.supplier_import is not None
    assert row.values["label_id"] == "LPNA000184"


def test_parser_applies_d1_without_supplier_metadata() -> None:
    parsed = parse_local_csv(
        _csv_bytes(
            {
                "capture_photo_id": "photo-d1",
                "internal_code": "SKU-1",
                "label_id": "LPNA000184",
                "quantity": "1",
                "notes": "plain-note",
            }
        )
    )
    assert "label_id:invalid_format" in parsed.rows[0].errors


def test_golden_item_preview_accepted() -> None:
    preview, _, _, _ = _preview_stack()
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "capture_photo_id": "photo-item",
                "internal_code": "SKU773421",
                "label_id": "LPNA000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="ITEM",
                    raw_payload="LPNA000184|SKU773421|24",
                    profile_id=ITEM_PROFILE_ID,
                    profile_version=10,
                ),
            }
        ),
    )
    assert record.rejected_rows == 0
    row = record.rows[0]
    assert row.status == "PREVIEW_VALID"
    assert row.internal_code == "SKU773421"
    assert row.label_id == "LPNA000184"
    assert row.quantity == 24
    assert_package_csv_rows_ready(record.rows)


def test_golden_position_preview_valid_not_productive() -> None:
    preview, _, _, _ = _preview_stack()
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "capture_photo_id": "photo-pos",
                "position_code": "A04-R-02",
                "position_label_id": "A04-R-02",
                "position_payload_raw": "A04-R-02|04|RIGHT|02",
                "source": "LOCAL_POSITION_LABEL",
                "quantity_status": "NOT_APPLICABLE",
                "notes": _supplier_notes(
                    label_kind="POSITION",
                    raw_payload="A04-R-02|04|RIGHT|02",
                    profile_id=POS_PROFILE_ID,
                    profile_version=3,
                ),
            }
        ),
    )
    assert record.rejected_rows == 0
    row = record.rows[0]
    assert row.status == "PREVIEW_VALID"
    assert row.internal_code in (None, "")
    assert row.position_code == "A04-R-02"


def test_mixed_golden_package_preview() -> None:
    preview, _, _, _ = _preview_stack()
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "capture_photo_id": "photo-item",
                "internal_code": "SKU773421",
                "label_id": "LPNA000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="ITEM",
                    raw_payload="LPNA000184|SKU773421|24",
                    profile_id=ITEM_PROFILE_ID,
                    profile_version=10,
                ),
            },
            {
                "capture_photo_id": "photo-pos",
                "position_code": "A04-R-02",
                "position_label_id": "A04-R-02",
                "position_payload_raw": "A04-R-02|04|RIGHT|02",
                "source": "LOCAL_POSITION_LABEL",
                "quantity_status": "NOT_APPLICABLE",
                "notes": _supplier_notes(
                    label_kind="POSITION",
                    raw_payload="A04-R-02|04|RIGHT|02",
                    profile_id=POS_PROFILE_ID,
                    profile_version=3,
                ),
            },
        ),
    )
    assert record.rejected_rows == 0
    products = [r for r in record.rows if r.internal_code]
    positions = [r for r in record.rows if r.detection_source == "LOCAL_POSITION_LABEL"]
    assert len(products) == 1
    assert len(positions) == 1
    assert_package_csv_rows_ready(record.rows)


def test_historical_v10_used_when_v11_active() -> None:
    profiles = MemorySupplierExtractionProfileRepository()
    _seed_profiles(profiles, include_item_v11=True)
    preview, _, _, _ = _preview_stack(profiles=profiles)
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "internal_code": "SKU773421",
                "label_id": "LPNA000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="ITEM",
                    raw_payload="LPNA000184|SKU773421|24",
                    profile_id=ITEM_PROFILE_ID,
                    profile_version=10,
                ),
            }
        ),
    )
    assert record.rejected_rows == 0
    assert record.rows[0].internal_code == "SKU773421"


def test_missing_historical_profile_fails_closed() -> None:
    profiles = MemorySupplierExtractionProfileRepository()
    _seed_profiles(profiles, include_item_v10=False)
    preview, _, _, _ = _preview_stack(profiles=profiles)
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "internal_code": "SKU773421",
                "label_id": "LPNA000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="ITEM",
                    raw_payload="LPNA000184|SKU773421|24",
                    profile_id=ITEM_PROFILE_ID,
                    profile_version=10,
                ),
            }
        ),
    )
    assert record.rejected_rows == 1
    assert "SUPPLIER_PROFILE_VERSION_NOT_AVAILABLE" in record.rows[0].validation_errors


def test_wrong_supplier_profile_rejected() -> None:
    profiles = MemorySupplierExtractionProfileRepository()
    _seed_profiles(profiles, item_supplier_id="other-supplier")
    preview, _, _, _ = _preview_stack(profiles=profiles)
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "internal_code": "SKU773421",
                "label_id": "LPNA000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="ITEM",
                    raw_payload="LPNA000184|SKU773421|24",
                    profile_id=ITEM_PROFILE_ID,
                    profile_version=10,
                    client_supplier_id=SUPPLIER_ID,
                ),
            }
        ),
    )
    assert record.rejected_rows == 1
    assert "supplier_profile:scope_mismatch" in record.rows[0].validation_errors


@pytest.mark.parametrize(
    "field,value",
    [
        ("internal_code", "SKU999999"),
        ("quantity", "999"),
        ("label_id", "LPNA999999"),
    ],
)
def test_semantic_tamper_rejected(field: str, value: str) -> None:
    preview, _, _, _ = _preview_stack()
    row = {
        "internal_code": "SKU773421",
        "label_id": "LPNA000184",
        "quantity": "24",
        "notes": _supplier_notes(
            label_kind="ITEM",
            raw_payload="LPNA000184|SKU773421|24",
            profile_id=ITEM_PROFILE_ID,
            profile_version=10,
        ),
        field: value,
    }
    record = preview.execute(inventory_id=INVENTORY_ID, content=_csv_bytes(row))
    assert record.rejected_rows == 1
    assert any("supplier_semantic_mismatch" in err for err in record.rows[0].validation_errors)


def test_wrong_item_prefix_rejected() -> None:
    preview, _, _, _ = _preview_stack()
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "internal_code": "SKU773421",
                "label_id": "XXXX000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="ITEM",
                    raw_payload="XXXX000184|SKU773421|24",
                    profile_id=ITEM_PROFILE_ID,
                    profile_version=10,
                ),
            }
        ),
    )
    assert record.rejected_rows == 1
    assert "LABEL_PREFIX_MISMATCH" in record.rows[0].validation_errors


def test_wrong_segment_count_rejected() -> None:
    preview, _, _, _ = _preview_stack()
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "internal_code": "SKU773421",
                "label_id": "LPNA000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="ITEM",
                    raw_payload="LPNA000184|SKU773421",
                    profile_id=ITEM_PROFILE_ID,
                    profile_version=10,
                ),
            }
        ),
    )
    assert record.rejected_rows == 1


def test_item_raw_with_position_profile_rejected() -> None:
    preview, _, _, _ = _preview_stack()
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "internal_code": "SKU773421",
                "label_id": "LPNA000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="POSITION",
                    raw_payload="LPNA000184|SKU773421|24",
                    profile_id=POS_PROFILE_ID,
                    profile_version=3,
                ),
            }
        ),
    )
    assert record.rejected_rows == 1


def test_d1_valid_label_still_accepted() -> None:
    label_id = generate_product_label_id()
    preview, _, _, _ = _preview_stack()
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "internal_code": "SKU-D1",
                "label_id": label_id,
                "quantity": "3",
                "notes": "ok",
            }
        ),
    )
    assert record.rejected_rows == 0
    assert record.rows[0].label_id == label_id


def test_d1_invalid_letter_still_rejected_without_metadata() -> None:
    parsed = parse_local_csv(
        _csv_bytes(
            {
                "internal_code": "SKU-1",
                "label_id": "LPNA000184",
                "quantity": "1",
            }
        )
    )
    assert "label_id:invalid_format" in parsed.rows[0].errors


def test_preview_confirm_parity() -> None:
    preview, import_repo, _, _ = _preview_stack()
    writer = MemoryLocalCsvInventoryResultWriter()
    confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=writer,
        clock=FixedClock(),
        enabled=True,
    )
    record = preview.execute(
        inventory_id=INVENTORY_ID,
        content=_csv_bytes(
            {
                "internal_code": "SKU773421",
                "label_id": "LPNA000184",
                "quantity": "24",
                "notes": _supplier_notes(
                    label_kind="ITEM",
                    raw_payload="LPNA000184|SKU773421|24",
                    profile_id=ITEM_PROFILE_ID,
                    profile_version=10,
                ),
            }
        ),
    )
    confirmed, _duplicate = confirm.execute(
        inventory_id=INVENTORY_ID,
        export_id=record.export_id,
    )
    assert confirmed.status == "CONFIRMED"
    results = writer.list_for_import(confirmed.id)
    assert len(results) == 1
    assert results[0].internal_code == "SKU773421"
    assert results[0].quantity == 24
