"""Tests for inventory-level CSV export (v3 consolidated results)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import pytest

from src.application.errors import InventoryNotFoundError
from src.application.services.csv_inventory_exporter import (
    INVENTORY_RESULTS_CSV_FIELDS,
    INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS,
    UTF8_BOM,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.inventories.export_inventory_results import (
    ExportAisleResultsCsvUseCase,
    ExportInventoryResultsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)

NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
NOW_EARLY = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
NOW_LATE = datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc)


def _uc(
    inv: Inventory | None = None,
    aisles: list[Aisle] | None = None,
    positions: list[Position] | None = None,
    products: list[ProductRecord] | None = None,
    jobs: list[Job] | None = None,
) -> ExportInventoryResultsUseCase:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    job_repo = MemoryJobRepository()
    if inv:
        inv_repo.save(inv)
    for a in aisles or []:
        aisle_repo.save(a)
    for p in positions or []:
        pos_repo.save(p)
    for pr in products or []:
        prod_repo.save(pr)
    for j in jobs or []:
        job_repo.save(j)
    return ExportInventoryResultsUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo, pos_repo),
    )


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
    assert [r["aisle_code"] for r in rows] == ["A1", "A2", "A10"]
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


def test_export_csv_sorting_is_type_safe_for_mixed_position_codes() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "B1", AisleStatus.COMPLETED, NOW, NOW)
    positions = [
        Position(
            id="p-10",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={
                "internal_code": "SKU-10",
                "final_quantity": 1,
                "pallet_id": "10",
            },
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
            detected_summary_json={
                "internal_code": "SKU-A1",
                "final_quantity": 1,
                "pallet_id": "A1",
            },
        ),
        Position(
            id="p-2",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={
                "internal_code": "SKU-2",
                "final_quantity": 1,
                "position_barcode": "2",
            },
        ),
        Position(
            id="p-b2",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={
                "internal_code": "SKU-B2",
                "final_quantity": 1,
                "entity_uid": "B2",
            },
        ),
    ]
    uc = _uc(inv=inv, aisles=[aisle], positions=positions)

    _, rows = _parse_csv(uc.execute_csv("inv-1"))

    assert [r["position_id"] for r in rows] == ["p-2", "p-10", "p-a1", "p-b2"]


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
    assert rows[0]["qty_inference_reason"] == ""
    assert rows[0]["product_display_label"] == "Early row"


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
    assert rows[0]["product_sku"] == "MERGE"
    assert rows[0]["detected_quantity"] == "5"
    assert rows[0]["final_quantity"] == "5"


def test_export_operational_csv_aligns_with_public_contract_fields() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "B1", AisleStatus.COMPLETED, NOW, NOW)
    pos = Position(
        id="p1",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id="ev-1",
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={
            "internal_code": "LEGACY",
            "review_display_label": "Legacy label",
            "position_barcode": "BC-1",
            "final_quantity": 4,
            "traceability_status": "valid",
            "source_image_id": "img-1",
        },
    )
    prod = ProductRecord(
        id="pr1",
        position_id="p1",
        sku="SKU-1",
        description="Display label",
        detected_quantity=4,
        corrected_quantity=6,
        confidence=0.9,
        created_at=NOW,
        updated_at=NOW,
        qty_source="manual_review",
        qty_inference_reason="operator",
    )
    uc = _uc(inv=inv, aisles=[aisle], positions=[pos], products=[prod])
    _, rows = _parse_csv(uc.execute_csv("inv-1"))
    assert rows == [
        {
            "inventory_id": "inv-1",
            "inventory_name": "Warehouse",
            "aisle_id": "a1",
            "aisle_code": "B1",
            "aisle_sequence": "1",
            "position_id": "p1",
            "position_status": "detected",
            "needs_review": "true",
            "position_code": "BC-1",
            "product_sku": "SKU-1",
            "product_display_label": "Display label",
            "barcode": "BC-1",
            "detected_quantity": "4",
            "corrected_quantity": "6",
            "final_quantity": "6",
            "qty_source": "manual_review",
            "qty_inference_reason": "",
            "traceability_status": "valid",
            "source_image_id": "img-1",
            "primary_evidence_id": "ev-1",
            "updated_at": NOW.isoformat(),
        }
    ]


def test_export_technical_csv_keeps_snapshot_fields_separate() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "B1", AisleStatus.COMPLETED, NOW, NOW)
    pos = Position(
        id="p1",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={
            "internal_code": "SKU-TECH",
            "review_display_label": "Tech label",
            "position_barcode": "BAR-1",
            "pallet_id": "PAL-1",
            "entity_uid": "job_1_e1",
            "entity_type": "PALLET",
            "count_status": "COUNTED",
            "raw_qty": "4x",
            "qty_parse_status": "invalid",
            "qty_origin_field": "product_label_quantity",
            "aggregated_from_ids": ["p-a", "p-b"],
            "_audit": {"explicit_quantity_missing": True},
        },
    )
    uc = _uc(inv=inv, aisles=[aisle], positions=[pos])
    csv_text = uc.execute_csv("inv-1", technical=True)
    headers, rows = _parse_csv(csv_text)
    assert headers == list(INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS)
    assert rows[0]["internal_code"] == "SKU-TECH"
    assert rows[0]["review_display_label"] == "Tech label"
    assert rows[0]["position_barcode"] == "BAR-1"
    assert rows[0]["pallet_id"] == "PAL-1"
    assert rows[0]["aggregated_from_ids"] == "p-a|p-b"
    assert '"explicit_quantity_missing": true' in rows[0]["audit_json"]


def test_export_only_includes_operational_job_slice_when_pointer_set() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle(
        "a1",
        "inv-1",
        "B1",
        AisleStatus.COMPLETED,
        NOW,
        NOW,
        operational_job_id="j-op",
    )
    positions = [
        Position(
            id="p-op",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "IN", "final_quantity": 1, "pallet_id": "A"},
            job_id="j-op",
        ),
        Position(
            id="p-other",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW_LATE,
            updated_at=NOW_LATE,
            detected_summary_json={"internal_code": "OUT", "final_quantity": 2, "pallet_id": "B"},
            job_id="j-bench",
        ),
    ]
    job_op = Job(
        id="j-op",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=NOW,
        updated_at=NOW,
    )
    uc = _uc(inv=inv, aisles=[aisle], positions=positions, jobs=[job_op])
    _, rows = _parse_csv(uc.execute_csv("inv-1"))
    assert len(rows) == 1
    assert rows[0]["position_id"] == "p-op"


def test_export_aisle_csv_explicit_job_matches_non_operational_slice() -> None:
    """Single-aisle export with job_id must match that run's positions only (no duplicate runs)."""
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle(
        "a1",
        "inv-1",
        "B1",
        AisleStatus.COMPLETED,
        NOW,
        NOW,
        operational_job_id="j-op",
    )
    positions = [
        Position(
            id="p-op",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "IN", "final_quantity": 1, "pallet_id": "A"},
            job_id="j-op",
        ),
        Position(
            id="p-other",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW_LATE,
            updated_at=NOW_LATE,
            detected_summary_json={"internal_code": "OUT", "final_quantity": 2, "pallet_id": "B"},
            job_id="j-bench",
        ),
    ]
    job_op = Job(
        id="j-op",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=NOW,
        updated_at=NOW,
    )
    job_bench = Job(
        id="j-bench",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=NOW_LATE,
        updated_at=NOW_LATE,
    )
    inv_r = MemoryInventoryRepository()
    aisle_r = MemoryAisleRepository()
    pos_r = MemoryPositionRepository()
    prod_r = MemoryProductRecordRepository()
    job_r = MemoryJobRepository()
    inv_r.save(inv)
    aisle_r.save(aisle)
    for p in positions:
        pos_r.save(p)
    for j in (job_op, job_bench):
        job_r.save(j)
    uc2 = ExportAisleResultsCsvUseCase(
        inv_r,
        aisle_r,
        pos_r,
        prod_r,
        ResultContextResolver(job_r, pos_r),
    )
    _, rows = _parse_csv(uc2.execute_csv("inv-1", "a1", job_id="j-bench"))
    assert len(rows) == 1
    assert rows[0]["position_id"] == "p-other"
    assert rows[0]["product_sku"] == "OUT"
