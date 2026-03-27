"""Tests for inventory-level CSV export (v3 consolidated results)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import pytest

from src.application.errors import InventoryNotFoundError
from src.application.services.csv_inventory_exporter import INVENTORY_RESULTS_CSV_FIELDS, UTF8_BOM
from src.application.use_cases.export_inventory_results import ExportInventoryResultsUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository


NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
NOW_EARLY = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
NOW_LATE = datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc)


def _uc(
    inv: Inventory | None = None,
    aisles: list[Aisle] | None = None,
    positions: list[Position] | None = None,
    products: list[ProductRecord] | None = None,
) -> ExportInventoryResultsUseCase:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    if inv:
        inv_repo.save(inv)
    for a in aisles or []:
        aisle_repo.save(a)
    for p in positions or []:
        pos_repo.save(p)
    for pr in products or []:
        prod_repo.save(pr)
    return ExportInventoryResultsUseCase(inv_repo, aisle_repo, pos_repo, prod_repo)


def _parse_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    if text.startswith(UTF8_BOM):
        text = text[len(UTF8_BOM) :]
    r = csv.DictReader(io.StringIO(text))
    assert r.fieldnames is not None
    rows = list(r)
    return list(r.fieldnames), rows


def test_export_inventory_not_found_raises() -> None:
    uc = _uc()
    with pytest.raises(InventoryNotFoundError):
        uc.execute_csv("missing-inv")


def test_export_headers_only_when_no_aisles() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.DRAFT, NOW, NOW)
    uc = _uc(inv=inv, aisles=[], positions=[])
    csv_text = uc.execute_csv("inv-1")
    assert csv_text.startswith(UTF8_BOM)
    headers, rows = _parse_csv(csv_text)
    assert headers == list(INVENTORY_RESULTS_CSV_FIELDS)
    assert rows == []


def test_export_aisle_natural_sort_order() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisles = [
        Aisle("a10", "inv-1", "A10", AisleStatus.COMPLETED, NOW, NOW),
        Aisle("a2", "inv-1", "A2", AisleStatus.COMPLETED, NOW, NOW),
        Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW),
    ]
    positions = [
        Position(
            id="p-a10",
            aisle_id="a10",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "S10", "final_quantity": 1, "pallet_id": "P10"},
        ),
        Position(
            id="p-a2",
            aisle_id="a2",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "S2", "final_quantity": 1, "pallet_id": "P2"},
        ),
        Position(
            id="p-a1",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "S1", "final_quantity": 1, "pallet_id": "P1"},
        ),
    ]
    uc = _uc(inv=inv, aisles=aisles, positions=positions)
    _, rows = _parse_csv(uc.execute_csv("inv-1"))
    assert [r["aisle_name"] for r in rows] == ["A1", "A2", "A10"]
    assert [r["aisle_sequence"] for r in rows] == ["1", "2", "3"]


def test_export_positions_within_aisle_natural_sort_by_position_code() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "B1", AisleStatus.COMPLETED, NOW, NOW)
    positions = [
        Position(
            id="p-late",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={
                "internal_code": "SX",
                "final_quantity": 1,
                "pallet_id": "slot-10",
            },
        ),
        Position(
            id="p-early",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={
                "internal_code": "SY",
                "final_quantity": 1,
                "pallet_id": "slot-2",
            },
        ),
    ]
    uc = _uc(inv=inv, aisles=[aisle], positions=positions)
    _, rows = _parse_csv(uc.execute_csv("inv-1"))
    assert [r["position_id"] for r in rows] == ["p-early", "p-late"]


def test_export_final_quantity_prefers_corrected() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "B1", AisleStatus.COMPLETED, NOW, NOW)
    pos = Position(
        id="p1",
        aisle_id="a1",
        status=PositionStatus.REVIEWED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": "SKU-Z", "final_quantity": 4},
    )
    prod = ProductRecord(
        id="pr1",
        position_id="p1",
        sku="SKU-Z",
        description="Item Z",
        detected_quantity=4,
        corrected_quantity=9,
        confidence=0.9,
        created_at=NOW,
        updated_at=NOW,
        qty_source="manual_review",
    )
    uc = _uc(inv=inv, aisles=[aisle], positions=[pos], products=[prod])
    _, rows = _parse_csv(uc.execute_csv("inv-1"))
    assert len(rows) == 1
    assert rows[0]["final_quantity"] == "9"
    assert rows[0]["detected_quantity"] == "4"
    assert rows[0]["corrected_quantity"] == "9"


def test_export_qty_source_uses_display_primary_product() -> None:
    """Earliest product row by (created_at, id) drives qty provenance columns (matches list positions)."""
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "B1", AisleStatus.COMPLETED, NOW, NOW)
    pos = Position(
        id="p1",
        aisle_id="a1",
        status=PositionStatus.REVIEWED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": "SKU-DUAL", "final_quantity": 3},
    )
    prod_newer = ProductRecord(
        id="pr-late",
        position_id="p1",
        sku="SKU-DUAL",
        description="Late row",
        detected_quantity=3,
        confidence=0.9,
        created_at=NOW_LATE,
        updated_at=NOW_LATE,
        qty_source="detected",
        qty_inference_reason="from_llm",
    )
    prod_older = ProductRecord(
        id="pr-early",
        position_id="p1",
        sku="SKU-DUAL",
        description="Early row",
        detected_quantity=3,
        confidence=0.9,
        created_at=NOW_EARLY,
        updated_at=NOW_EARLY,
        qty_source="manual_review",
        qty_inference_reason="operator",
    )
    uc = _uc(inv=inv, aisles=[aisle], positions=[pos], products=[prod_newer, prod_older])
    _, rows = _parse_csv(uc.execute_csv("inv-1"))
    assert len(rows) == 1
    assert rows[0]["qty_source"] == "manual_review"
    assert rows[0]["qty_inference_reason"] == "operator"
    assert rows[0]["product_label"] == "Early row"


def test_export_excludes_deleted_positions() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "B1", AisleStatus.COMPLETED, NOW, NOW)
    positions = [
        Position(
            id="p-del",
            aisle_id="a1",
            status=PositionStatus.DELETED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "GONE", "final_quantity": 1},
        ),
        Position(
            id="p-ok",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "OK", "final_quantity": 2},
        ),
    ]
    uc = _uc(inv=inv, aisles=[aisle], positions=positions)
    _, rows = _parse_csv(uc.execute_csv("inv-1"))
    assert len(rows) == 1
    assert rows[0]["position_id"] == "p-ok"


def test_export_sku_consolidation_single_row() -> None:
    """Two raw positions same SKU consolidate like list endpoint."""
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "B1", AisleStatus.COMPLETED, NOW, NOW)
    positions = [
        Position(
            id="p-a",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "MERGE", "final_quantity": 2},
        ),
        Position(
            id="p-b",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "MERGE", "final_quantity": 3},
        ),
    ]
    uc = _uc(inv=inv, aisles=[aisle], positions=positions)
    _, rows = _parse_csv(uc.execute_csv("inv-1"))
    assert len(rows) == 1
    assert rows[0]["sku"] == "MERGE"
    assert rows[0]["detected_quantity"] == "5"
    assert rows[0]["final_quantity"] == "5"
