"""Unit tests for local CSV → aisle position materialization rules."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from src.application.ports.issued_product_label_repository import IssuedProductLabel
from src.application.services.local_csv_parser import parse_local_csv
from src.application.services.local_csv_position_materializer import (
    LocalCsvPositionMaterializer,
    is_inventory_line_result,
    position_id_for_productive,
    product_id_for_productive,
)
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.local_csv_import.entities import LocalCsvProductiveResult
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.domain.positions.entities import PositionStatus
from src.domain.product_labels.format import (
    build_product_label_payload,
    parse_product_label_payload,
)
from src.infrastructure.repositories.memory_inventory_counted_product_label_repository import (
    MemoryInventoryCountedProductLabelRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_issued_product_label_repository import (
    MemoryIssuedProductLabelRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
LABEL_ID = "A1B2C3D4E5"
ISSUED_SKU = "SKU100"
ISSUED_QTY = 4

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


def _issue(repo: MemoryIssuedProductLabelRepository, *, client_id: str = "client-a") -> None:
    payload = build_product_label_payload(
        label_id=LABEL_ID, internal_code=ISSUED_SKU, quantity=ISSUED_QTY
    )
    parsed = parse_product_label_payload(payload)
    repo.save(
        IssuedProductLabel(
            id="iss-1",
            client_id=client_id,
            label_id=LABEL_ID,
            internal_code=ISSUED_SKU,
            quantity=ISSUED_QTY,
            format_version="D1",
            checksum=str(parsed.checksum_received),
            payload=payload,
            created_at=NOW,
        )
    )


def _inventory_repo(*, client_id: str = "client-a") -> MemoryInventoryRepository:
    repo = MemoryInventoryRepository()
    repo.save(
        Inventory(
            id="inv-1",
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
            client_id=client_id,
        )
    )
    return repo


def _materializer(
    *,
    issued: MemoryIssuedProductLabelRepository | None = None,
    counted: MemoryInventoryCountedProductLabelRepository | None = None,
    inventory_repo: MemoryInventoryRepository | None = None,
    position_repo: MemoryPositionRepository | None = None,
    product_repo: MemoryProductRecordRepository | None = None,
) -> tuple[
    LocalCsvPositionMaterializer,
    MemoryPositionRepository,
    MemoryProductRecordRepository,
    MemoryInventoryCountedProductLabelRepository,
]:
    issued_repo = issued or MemoryIssuedProductLabelRepository()
    counted_repo = counted or MemoryInventoryCountedProductLabelRepository()
    pos = position_repo or MemoryPositionRepository()
    prod = product_repo or MemoryProductRecordRepository()
    mat = LocalCsvPositionMaterializer(
        position_repo=pos,
        product_record_repo=prod,
        counted_product_label_repo=counted_repo,
        issued_label_resolver=IssuedProductLabelResolver(issued_repo=issued_repo),
        inventory_repo=inventory_repo or _inventory_repo(),
    )
    return mat, pos, prod, counted_repo


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
        internal_code=ISSUED_SKU,
        quantity=ISSUED_QTY,
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


def _schema_11_csv(*, label_id: str = LABEL_ID) -> bytes:
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
            "internal_code": ISSUED_SKU,
            "quantity": str(ISSUED_QTY),
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
    mat, position_repo, product_repo, _ = _materializer()
    label = _result(
        id="label-1",
        detection_source="LOCAL_POSITION_LABEL",
        internal_code=None,
        quantity=None,
        quantity_status="MISSING",
        label_id=None,
    )
    # Simulate prior bug: label was materialized as an item
    mat._materialize_one(label, now=NOW)  # noqa: SLF001
    assert len(position_repo.list_by_aisle("aisle-1", job_id=None)) == 1

    product = _result(
        id="prod-2",
        position_code="pos_ABC",
        internal_code="22242925205",
        quantity=100000,
        label_id=None,
    )
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
    parsed = parse_local_csv(_schema_11_csv(label_id=LABEL_ID))
    assert parsed.schema_version == "1.1"
    assert parsed.rows[0].values.get("label_id") == LABEL_ID
    assert parsed.rows[0].errors == ()

    issued = MemoryIssuedProductLabelRepository()
    _issue(issued)
    mat, position_repo, product_repo, _ = _materializer(issued=issued)
    result = _result(id="prod-label-1", label_id=LABEL_ID)
    assert mat.materialize([result], now=NOW) == 1
    pos_id = position_id_for_productive("prod-label-1")
    products = list(product_repo.list_by_position(pos_id))
    assert len(products) == 1
    assert products[0].label_id == LABEL_ID
    assert products[0].id == product_id_for_productive("prod-label-1")
    assert products[0].sku == ISSUED_SKU
    assert products[0].detected_quantity == ISSUED_QTY

    # Rematerialize same productive row: claim fails, no second ProductRecord.
    assert mat.materialize([result], now=NOW) == 1
    products_again = list(product_repo.list_by_position(pos_id))
    assert len(products_again) == 1
    assert products_again[0].id == products[0].id

    # Different productive id with same label_id must not create another product.
    other = _result(id="prod-label-2", label_id=LABEL_ID, import_row_id="row-2")
    assert mat.materialize([other], now=NOW) == 0
    assert product_repo.get_by_id(product_id_for_productive("prod-label-2")) is None
    assert position_repo.get_by_id(position_id_for_productive("prod-label-2")) is None


def test_materialize_unknown_label_falls_back_to_csv_with_review() -> None:
    mat, position_repo, product_repo, _ = _materializer()
    assert mat.materialize([_result(label_id=LABEL_ID)], now=NOW) == 1
    pos = position_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.needs_review is True
    assert pos.detected_summary_json is not None
    assert pos.detected_summary_json.get("label_registry_status") == "unresolved"
    assert pos.detected_summary_json.get("label_authority") == "csv_fallback"
    product = product_repo.get_by_id(product_id_for_productive("prod-1"))
    assert product is not None
    assert product.label_id == LABEL_ID
    assert product.sku == ISSUED_SKU
    assert product.detected_quantity == ISSUED_QTY


def test_materialize_client_mismatch_falls_back_to_csv_with_review() -> None:
    issued = MemoryIssuedProductLabelRepository()
    _issue(issued, client_id="client-a")
    mat, position_repo, product_repo, _ = _materializer(
        issued=issued,
        inventory_repo=_inventory_repo(client_id="client-b"),
    )
    assert mat.materialize([_result(label_id=LABEL_ID)], now=NOW) == 1
    pos = position_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.needs_review is True
    product = product_repo.get_by_id(product_id_for_productive("prod-1"))
    assert product is not None
    assert product.sku == ISSUED_SKU


def test_materialize_sku_mismatch_falls_back_to_csv_with_review() -> None:
    issued = MemoryIssuedProductLabelRepository()
    _issue(issued)
    mat, position_repo, product_repo, _ = _materializer(issued=issued)
    assert (
        mat.materialize(
            [_result(label_id=LABEL_ID, internal_code="OTHER", quantity=ISSUED_QTY)],
            now=NOW,
        )
        == 1
    )
    pos = position_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.needs_review is True
    product = product_repo.get_by_id(product_id_for_productive("prod-1"))
    assert product is not None
    assert product.sku == "OTHER"
    assert product.detected_quantity == ISSUED_QTY


def test_materialize_qty_mismatch_falls_back_to_csv_with_review() -> None:
    issued = MemoryIssuedProductLabelRepository()
    _issue(issued)
    mat, position_repo, product_repo, _ = _materializer(issued=issued)
    assert (
        mat.materialize(
            [_result(label_id=LABEL_ID, internal_code=ISSUED_SKU, quantity=9)],
            now=NOW,
        )
        == 1
    )
    pos = position_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.needs_review is True
    product = product_repo.get_by_id(product_id_for_productive("prod-1"))
    assert product is not None
    assert product.detected_quantity == 9


def test_materialize_valid_claim() -> None:
    issued = MemoryIssuedProductLabelRepository()
    _issue(issued)
    mat, position_repo, product_repo, counted = _materializer(issued=issued)
    assert mat.materialize([_result(label_id=LABEL_ID)], now=NOW) == 1
    pos = position_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    product = product_repo.get_by_id(product_id_for_productive("prod-1"))
    assert product is not None
    assert product.label_id == LABEL_ID
    assert product.sku == ISSUED_SKU
    assert product.detected_quantity == ISSUED_QTY
    assert counted.get("aisle-1", LABEL_ID) is not None
