from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import pytest

from src.application.services.local_csv_parser import (
    LocalCsvDocumentError,
    parse_local_csv,
)
from src.application.use_cases.inventories.manage_local_csv_import import (
    LOCAL_CSV_INVENTORY_MISMATCH,
    ConfirmLocalCsvImport,
    LocalCsvImportError,
    PreviewLocalCsvImport,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    MemoryLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_local_csv_import_repository import (
    MemoryLocalCsvImportRepository,
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


class FixedClock:
    def now(self) -> datetime:
        return NOW


def _csv_bytes(
    *,
    export_id: str = "export-1",
    inventory_id: str = "inventory-1",
    session_id: str = "session-1",
    photo_id: str = "photo-1",
    notes: str = "ok",
    source: str = "LOCAL_CODE_SCAN",
    position_code: str = "A-01",
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
            "aisle_id": "aisle-1",
            "capture_session_id": session_id,
            "capture_photo_id": photo_id,
            "client_file_id": "file-1",
            "capture_order": "1",
            "captured_at": "2026-08-04T09:59:00Z",
            "position_code": position_code,
            "internal_code": "SKU-1",
            "quantity": "7",
            "quantity_status": "PRESENT",
            "detection_status": "DETECTED",
            "source": source,
            "requires_review": "false",
            "error_code": "",
            "notes": notes,
        }
    )
    return output.getvalue().encode()


def _use_cases() -> tuple[
    PreviewLocalCsvImport,
    ConfirmLocalCsvImport,
    MemoryLocalCsvImportRepository,
    MemoryLocalCsvInventoryResultWriter,
]:
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id="inventory-1",
            code="A",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    import_repo = MemoryLocalCsvImportRepository()
    writer = MemoryLocalCsvInventoryResultWriter()
    preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=writer,
        clock=FixedClock(),
        enabled=True,
    )
    return preview, confirm, import_repo, writer


def test_parser_accepts_mobile_detection_source() -> None:
    parsed = parse_local_csv(_csv_bytes(source="LOCAL_CODE_SCAN"))

    assert parsed.schema_version == "1"
    assert parsed.rows[0].detection_source == "LOCAL_CODE_SCAN"
    assert parsed.rows[0].ingestion_source == INGESTION_SOURCE_LOCAL_CSV_IMPORT
    assert parsed.rows[0].errors == ()


def test_parser_accepts_legacy_local_csv_import_source_as_pending() -> None:
    parsed = parse_local_csv(_csv_bytes(source="LOCAL_CSV_IMPORT"))

    assert parsed.rows[0].detection_source == "LOCAL_PENDING"
    assert parsed.rows[0].ingestion_source == INGESTION_SOURCE_LOCAL_CSV_IMPORT
    assert "source:legacy_LOCAL_CSV_IMPORT_treated_as_LOCAL_PENDING" in parsed.rows[0].warnings


def test_parser_rejects_malformed_rfc4180_csv() -> None:
    content = (",".join(HEADERS) + "\r\n" + '"unterminated').encode()

    with pytest.raises(LocalCsvDocumentError) as exc:
        parse_local_csv(content)

    assert exc.value.code == "CSV_MALFORMED"


def test_preview_rejects_wrong_path_inventory() -> None:
    preview, _, _, _ = _use_cases()

    with pytest.raises(LocalCsvImportError) as exc:
        preview.execute(
            inventory_id="inventory-1",
            content=_csv_bytes(inventory_id="inventory-other"),
        )

    assert exc.value.code == LOCAL_CSV_INVENTORY_MISMATCH


def test_formula_cell_is_neutralized_and_reported() -> None:
    preview, _, _, _ = _use_cases()

    record = preview.execute(
        inventory_id="inventory-1",
        content=_csv_bytes(notes="=HYPERLINK(\"https://invalid\")"),
    )

    assert record.rows[0].notes == "'=HYPERLINK(\"https://invalid\")"
    assert "notes:csv_formula_neutralized" in record.rows[0].validation_warnings
    assert record.rows[0].status == "PREVIEW_VALID"
    assert record.rows[0].detection_source == "LOCAL_CODE_SCAN"
    assert record.rows[0].ingestion_source == INGESTION_SOURCE_LOCAL_CSV_IMPORT


def test_preview_does_not_apply_productive_results() -> None:
    preview, _, _, writer = _use_cases()
    preview.execute(inventory_id="inventory-1", content=_csv_bytes())
    assert writer.list_for_inventory("inventory-1") == ()


def test_confirm_applies_productive_results_and_is_idempotent() -> None:
    preview, confirm, _, writer = _use_cases()
    staged = preview.execute(inventory_id="inventory-1", content=_csv_bytes())

    first, first_duplicate = confirm.execute(
        inventory_id="inventory-1",
        export_id=staged.export_id,
        confirmed_by_user_id="user-1",
    )
    second, second_duplicate = confirm.execute(
        inventory_id="inventory-1", export_id=staged.export_id
    )

    assert first.status == "CONFIRMED"
    assert first.rows[0].status == "IMPORTED"
    assert first.rows[0].productive_result_id is not None
    assert first.confirmed_by_user_id == "user-1"
    assert first_duplicate is False
    assert second.id == first.id
    assert second_duplicate is True
    results = writer.list_for_inventory("inventory-1")
    assert len(results) == 1
    assert results[0].ingestion_source == INGESTION_SOURCE_LOCAL_CSV_IMPORT
    assert results[0].detection_source == "LOCAL_CODE_SCAN"
    assert results[0].has_image_evidence is False
    assert results[0].quantity == 7


def test_confirm_skips_existing_secondary_capture_key() -> None:
    preview, confirm, _, writer = _use_cases()
    first = preview.execute(inventory_id="inventory-1", content=_csv_bytes())
    confirm.execute(inventory_id="inventory-1", export_id=first.export_id)
    second = preview.execute(
        inventory_id="inventory-1",
        content=_csv_bytes(export_id="export-2"),
    )

    confirmed, _ = confirm.execute(
        inventory_id="inventory-1",
        export_id=second.export_id,
        conflict_policy="SKIP",
    )

    assert confirmed.duplicate_rows == 1
    assert confirmed.rows[0].status == "DUPLICATE"
    assert len(writer.list_for_inventory("inventory-1")) == 1


def test_empty_position_forces_requires_review_on_productive() -> None:
    preview, confirm, _, writer = _use_cases()
    staged = preview.execute(
        inventory_id="inventory-1",
        content=_csv_bytes(position_code=""),
    )
    confirm.execute(inventory_id="inventory-1", export_id=staged.export_id)
    result = writer.list_for_inventory("inventory-1")[0]
    assert result.requires_review is True
