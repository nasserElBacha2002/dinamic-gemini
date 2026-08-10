"""Unit tests for local CSV → aisle position materialization rules."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import pytest

from src.application.errors import ProductLabelClaimRepositoryUnavailableError
from src.application.services.local_csv_parser import parse_local_csv
from src.application.services.local_csv_position_materializer import (
    LocalCsvPositionMaterializer,
    is_inventory_line_result,
    position_id_for_productive,
    product_id_for_productive,
)
from src.domain.local_csv_import.entities import LocalCsvProductiveResult
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.domain.positions.entities import PositionStatus
from src.infrastructure.repositories.memory_inventory_counted_product_label_repository import (
    MemoryInventoryCountedProductLabelRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

HEADERS_V11 = (
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
)


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


def _schema_11_csv(*, label_id: str = "A1B2C3D4E5") -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS_V11, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(
        {
            "schema_version": "1.1",
            "export_id": "export-label-1",
            "exported_at": "2026-08-04T10:00:00Z",
            "device_id": "device-1",
            "inventory_id": "inventory-1",
            "aisle_id": "aisle-1",
            "capture_session_id": "session-1",
            "capture_photo_id": "photo-1",
            "client_file_id": "file-1",
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
            "label_id": label_id,
        }
    )
    return output.getvalue().encode()


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


def test_schema_11_parse_and_materialize_claims_label_once() -> None:
    parsed = parse_local_csv(_schema_11_csv(label_id="A1B2C3D4E5"))
    assert parsed.schema_version == "1.1"
    assert parsed.rows[0].values.get("label_id") == "A1B2C3D4E5"
    assert parsed.rows[0].errors == ()

    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    counted = MemoryInventoryCountedProductLabelRepository()
    mat = LocalCsvPositionMaterializer(
        position_repo=position_repo,
        product_record_repo=product_repo,
        counted_product_label_repo=counted,
    )
    result = _result(id="prod-label-1", label_id="A1B2C3D4E5")
    assert mat.materialize([result], now=NOW) == 1
    pos_id = position_id_for_productive("prod-label-1")
    products = list(product_repo.list_by_position(pos_id))
    assert len(products) == 1
    assert products[0].label_id == "A1B2C3D4E5"
    assert products[0].id == product_id_for_productive("prod-label-1")

    # Rematerialize same productive row: claim fails, no second ProductRecord.
    assert mat.materialize([result], now=NOW) == 1
    products_again = list(product_repo.list_by_position(pos_id))
    assert len(products_again) == 1
    assert products_again[0].id == products[0].id

    # Different productive id with same label_id must not create another product.
    other = _result(id="prod-label-2", label_id="A1B2C3D4E5", import_row_id="row-2")
    assert mat.materialize([other], now=NOW) == 0
    assert product_repo.get_by_id(product_id_for_productive("prod-label-2")) is None


def test_materialize_with_label_id_requires_counted_repo() -> None:
    mat = LocalCsvPositionMaterializer(
        position_repo=MemoryPositionRepository(),
        product_record_repo=MemoryProductRecordRepository(),
        counted_product_label_repo=None,
    )
    with pytest.raises(ProductLabelClaimRepositoryUnavailableError):
        mat.materialize([_result(label_id="A1B2C3D4E5")], now=NOW)
