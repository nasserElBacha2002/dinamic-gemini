"""Unit tests for package CSV row gate."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.services.local_inventory_package_row_gate import (
    assert_package_csv_rows_ready,
)
from src.domain.local_csv_import.entities import LocalCsvImportRow
from src.domain.local_inventory_package.errors import LocalInventoryPackageImportError

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def _row(
    *,
    status: str = "PREVIEW_VALID",
    detection_source: str = "LOCAL_CODE_SCAN",
    internal_code: str | None = "SKU-1",
    validation_errors: tuple[str, ...] = (),
    row_number: int = 2,
) -> LocalCsvImportRow:
    return LocalCsvImportRow(
        id=f"row-{row_number}",
        import_id="import-1",
        row_number=row_number,
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        capture_session_id="session-1",
        capture_photo_id=f"photo-{row_number}",
        client_file_id=f"file-{row_number}",
        capture_order=row_number,
        captured_at=NOW,
        position_code="A-01",
        internal_code=internal_code,
        quantity=1,
        quantity_status="PRESENT",
        detection_status="RESOLVED",
        detection_source=detection_source,
        ingestion_source="LOCAL_CSV_IMPORT",
        requires_review=False,
        error_code=None,
        notes=None,
        status=status,
        validation_errors=validation_errors,
        validation_warnings=(),
    )


def test_gate_passes_with_productive_code_scan() -> None:
    assert_package_csv_rows_ready(
        [
            _row(detection_source="LOCAL_POSITION_LABEL", internal_code=None),
            _row(internal_code="SKU-1"),
        ]
    )


def test_gate_surfaces_schema_version_unsupported_in_detail() -> None:
    with pytest.raises(LocalInventoryPackageImportError) as exc:
        assert_package_csv_rows_ready(
            [
                _row(
                    status="REJECTED",
                    validation_errors=("schema_version:unsupported",),
                    row_number=2,
                ),
                _row(
                    status="REJECTED",
                    validation_errors=(
                        "schema_version:unsupported",
                        "secondary_key:duplicate_in_file",
                    ),
                    row_number=3,
                ),
            ]
        )
    assert exc.value.code == "PACKAGE_NO_PRODUCTIVE_ROWS"
    detail = str(exc.value)
    assert "schema_version:unsupported×2" in detail
    assert "secondary_key:duplicate_in_file×1" in detail
    assert "2 rejected row(s)" in detail
