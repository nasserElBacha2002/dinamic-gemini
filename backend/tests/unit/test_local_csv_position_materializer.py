"""Unit tests for local CSV → aisle position materialization rules."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.local_csv_position_materializer import (
    LocalCsvPositionMaterializer,
    is_inventory_line_result,
    position_id_for_productive,
)
from src.domain.local_csv_import.entities import LocalCsvProductiveResult
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.domain.positions.entities import PositionStatus
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def _result(**overrides: object) -> LocalCsvProductiveResult:
    base = dict(
        id="prod-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        import_id="imp-1",
        import_row_id="row-1",
        capture_session_id="sess-1",
        capture_photo_id="photo-1",
        client_file_id="file-1",
        capture_order=1,
        position_code="pos_ABC",
        internal_code="SKU-1",
        quantity=3,
        quantity_status="PRESENT",
        detection_status="RESOLVED",
        detection_source="LOCAL_CODE_SCAN",
        ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
        requires_review=False,
        has_image_evidence=True,
        confirmed_by_user_id="user-1",
        created_at=NOW,
        updated_at=NOW,
        source_asset_id="asset-1",
    )
    base.update(overrides)
    return LocalCsvProductiveResult(**base)  # type: ignore[arg-type]


def test_position_label_is_not_an_inventory_line() -> None:
    label = _result(
        id="label-1",
        detection_source="LOCAL_POSITION_LABEL",
        internal_code=None,
        quantity=None,
        quantity_status="MISSING",
    )
    product = _result(id="prod-2", detection_source="LOCAL_CODE_SCAN")
    assert is_inventory_line_result(label) is False
    assert is_inventory_line_result(product) is True


def test_materialize_skips_position_label_and_retires_prior_item() -> None:
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    mat = LocalCsvPositionMaterializer(
        position_repo=position_repo,
        product_record_repo=product_repo,
    )
    label = _result(
        id="label-1",
        detection_source="LOCAL_POSITION_LABEL",
        internal_code=None,
        quantity=None,
        quantity_status="MISSING",
    )
    # Simulate prior bug: label was materialized as an item
    mat._materialize_one(label, now=NOW)  # noqa: SLF001
    assert len(position_repo.list_by_aisle("aisle-1", job_id=None)) == 1

    product = _result(id="prod-2", position_code="pos_ABC", internal_code="22242925205", quantity=100000)
    written = mat.materialize([label, product], now=NOW)
    assert written == 1
    positions = position_repo.list_by_aisle("aisle-1", job_id=None)
    assert len(positions) == 1
    assert positions[0].id == position_id_for_productive("prod-2")
    assert positions[0].corrected_position_code == "pos_ABC"
    products = product_repo.list_by_position(positions[0].id)
    assert products[0].sku == "22242925205"
    assert products[0].detected_quantity == 100000
    summary = positions[0].detected_summary_json or {}
    assert summary.get("source_asset_id") == "asset-1"
    assert summary.get("traceability_status") == "valid"
    assert summary.get("has_valid_evidence") is True
    assert positions[0].primary_evidence_id == "asset-1"

    retired = position_repo.get_by_id(position_id_for_productive("label-1"))
    assert retired is not None
    assert retired.status == PositionStatus.DELETED
