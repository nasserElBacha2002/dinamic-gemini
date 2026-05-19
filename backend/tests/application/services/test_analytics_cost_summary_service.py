"""Service tests for analytics cost-summary aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.dto.analytics_cost_dto import AnalyticsCostSummaryFilters
from src.application.errors import AnalyticsScopeValidationError
from src.application.services.analytics_cost_counted_quantity import (
    AnalyticsCostCountedQuantityService,
    CountedQuantityScope,
)
from src.application.services.analytics_cost_summary_service import AnalyticsCostSummaryService
from src.application.services.analytics_cost_warnings import (
    COUNTED_QUANTITY_IS_OPERATIONAL_CURRENT_STATE,
    COUNTED_QUANTITY_NOT_AVAILABLE,
    COUNTED_QUANTITY_PARTIAL_NOT_RETURNED,
    COUNTED_QUANTITY_SCOPE_CAPPED,
    INVALID_COMPUTED_COST_PRESENT,
    PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE,
)
from src.application.services.result_context_resolver import ResultContextResolver
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


def _utc(**kwargs) -> datetime:
    return datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc).replace(**kwargs)


def _cost_snapshot(total: str = "1.00000000", status: str = "exact") -> dict:
    return {
        "llm_cost_snapshot": {
            "provider": "gemini",
            "model": "gemini-2.0",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cached_input_tokens": 0,
                "cache_write_tokens": 0,
                "thinking_tokens": 0,
                "tool_request_count": 0,
                "image_input_count": 0,
                "audio_input_tokens": 0,
                "video_input_tokens": 0,
            },
            "pricing_snapshot": {"billing_currency": "USD"},
            "computed_cost": {"total_cost": total, "currency": "USD"},
            "capture_status": status,
            "capture_notes": [],
        }
    }


@pytest.fixture
def cost_setup():
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    pos_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()

    inv = Inventory(
        id="inv-1",
        name="Warehouse",
        status=InventoryStatus.DRAFT,
        created_at=_utc(),
        updated_at=_utc(),
        completed_at=None,
        client_id="client-1",
    )
    inv_repo.save(inv)
    aisle = Aisle(
        id="aisle-1",
        inventory_id=inv.id,
        code="A1",
        status=AisleStatus.PROCESSED,
        created_at=_utc(),
        updated_at=_utc(),
        client_supplier_id="supplier-1",
    )
    aisle_repo.save(aisle)
    pos = Position(
        id="pos-1",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=_utc(),
        updated_at=_utc(),
        detected_summary_json={"traceability_status": "valid", "quantity": 3},
    )
    pos_repo.save(pos)
    product_repo.save(
        ProductRecord(
            id="prod-1",
            position_id=pos.id,
            sku="SKU-1",
            description="",
            detected_quantity=3,
            corrected_quantity=3,
            confidence=0.9,
            created_at=_utc(),
            updated_at=_utc(),
        )
    )

    def _job(
        job_id: str,
        *,
        total: str | None = "2.00000000",
        status: str = "exact",
        provider: str = "gemini",
        model: str = "gemini-2.0",
        finished: datetime | None = None,
        created: datetime | None = None,
        aisle_id: str | None = None,
    ) -> Job:
        result = _cost_snapshot(total, status) if total is not None else {}
        return Job(
            id=job_id,
            target_type="aisle",
            target_id=aisle_id or aisle.id,
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=created or _utc(),
            updated_at=_utc(),
            started_at=_utc(),
            finished_at=finished or _utc(),
            result_json=result if total is not None else None,
            provider_name=provider,
            model_name=model,
        )

    quantity_svc = AnalyticsCostCountedQuantityService(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=pos_repo,
        product_record_repo=product_repo,
        result_context_resolver=ResultContextResolver(job_repo=job_repo, position_repo=pos_repo),
    )
    svc = AnalyticsCostSummaryService(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inventory_repo=inv_repo,
        counted_quantity_service=quantity_svc,
    )
    return {
        "svc": svc,
        "job_repo": job_repo,
        "aisle": aisle,
        "inv": inv,
        "job_factory": _job,
        "quantity_svc": quantity_svc,
    }


def _filters(**kwargs) -> AnalyticsCostSummaryFilters:
    base = {
        "finished_from": _utc() - timedelta(days=1),
        "finished_to": _utc() + timedelta(days=1),
    }
    base.update(kwargs)
    return AnalyticsCostSummaryFilters(**base)


def test_aggregate_totals_and_provider_grouping(cost_setup) -> None:
    job_repo = cost_setup["job_repo"]
    job_repo.save(cost_setup["job_factory"]("job-1", total="1.00000000"))
    job_repo.save(cost_setup["job_factory"]("job-2", total="2.00000000", provider="openai", model="gpt-4o"))
    job_repo.save(cost_setup["job_factory"]("job-3", total=None, status="missing"))

    result = cost_setup["svc"].build(_filters(inventory_id=cost_setup["inv"].id))

    assert result.totals.jobs_total == 3
    assert result.totals.jobs_with_cost == 2
    assert result.totals.total_cost == Decimal("3.00000000")
    assert result.totals.total_counted_quantity is not None
    assert COUNTED_QUANTITY_IS_OPERATIONAL_CURRENT_STATE in result.warnings
    assert PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE in result.warnings
    for row in result.by_provider_model:
        assert row.total_counted_quantity is None
        assert row.cost_per_counted_unit is None


def test_unavailable_numeric_cost_not_summed(cost_setup) -> None:
    job_repo = cost_setup["job_repo"]
    job_repo.save(cost_setup["job_factory"]("job-1", total="99.00000000", status="unavailable"))

    result = cost_setup["svc"].build(_filters(inventory_id=cost_setup["inv"].id))

    assert result.totals.jobs_total == 1
    assert result.totals.jobs_with_unavailable_cost == 1
    assert result.totals.jobs_with_cost == 0
    assert result.totals.total_cost is None


def test_invalid_computed_cost_warning_surfaced(cost_setup) -> None:
    job_repo = cost_setup["job_repo"]
    job_repo.save(cost_setup["job_factory"]("job-1", total="not-a-number", status="exact"))

    result = cost_setup["svc"].build(_filters(inventory_id=cost_setup["inv"].id))

    assert INVALID_COMPUTED_COST_PRESENT in result.warnings
    assert result.totals.jobs_with_cost == 0


def test_job_created_before_range_finished_inside_included(cost_setup) -> None:
    job_repo = cost_setup["job_repo"]
    job_repo.save(
        cost_setup["job_factory"](
            "job-late-finish",
            created=_utc() - timedelta(days=60),
            finished=_utc(),
        )
    )

    result = cost_setup["svc"].build(_filters(inventory_id=cost_setup["inv"].id))

    assert result.totals.jobs_total == 1
    assert result.totals.total_cost == Decimal("2.00000000")


def test_client_id_filter(cost_setup) -> None:
    job_repo = cost_setup["job_repo"]
    job_repo.save(cost_setup["job_factory"]("job-1"))

    result = cost_setup["svc"].build(_filters(inventory_id=cost_setup["inv"].id, client_id="client-1"))
    assert result.totals.jobs_total == 1

    result_other = cost_setup["svc"].build(
        _filters(inventory_id=cost_setup["inv"].id, client_id="other-client")
    )
    assert result_other.totals.jobs_total == 0


def test_client_supplier_id_filter(cost_setup) -> None:
    job_repo = cost_setup["job_repo"]
    job_repo.save(cost_setup["job_factory"]("job-1"))

    result = cost_setup["svc"].build(
        _filters(inventory_id=cost_setup["inv"].id, client_supplier_id="supplier-1")
    )
    assert result.totals.jobs_total == 1

    result_other = cost_setup["svc"].build(
        _filters(inventory_id=cost_setup["inv"].id, client_supplier_id="other-supplier")
    )
    assert result_other.totals.jobs_total == 0


def test_aisle_inventory_scope_validation_fails(cost_setup) -> None:
    other_inv = Inventory(
        id="inv-2",
        name="Other",
        status=InventoryStatus.DRAFT,
        created_at=_utc(),
        updated_at=_utc(),
        completed_at=None,
    )
    cost_setup["svc"]._inventory_repo.save(other_inv)
    with pytest.raises(AnalyticsScopeValidationError):
        cost_setup["svc"].build(
            _filters(inventory_id=other_inv.id, aisle_id=cost_setup["aisle"].id)
        )


def test_capped_quantity_returns_null(cost_setup, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_quantity = MagicMock()
    mock_quantity.compute.return_value = CountedQuantityScope(
        total_counted_quantity=None,
        by_inventory_id={},
        by_aisle_id={},
        warnings=(COUNTED_QUANTITY_SCOPE_CAPPED, COUNTED_QUANTITY_PARTIAL_NOT_RETURNED, COUNTED_QUANTITY_NOT_AVAILABLE),
    )
    monkeypatch.setattr(cost_setup["svc"], "_quantity", mock_quantity)
    cost_setup["job_repo"].save(cost_setup["job_factory"]("job-1"))
    result = cost_setup["svc"].build(_filters(inventory_id=cost_setup["inv"].id))
    assert result.totals.total_counted_quantity is None
    assert result.totals.cost_per_counted_unit is None
    assert COUNTED_QUANTITY_SCOPE_CAPPED in result.warnings


def test_inventory_and_provider_filters(cost_setup) -> None:
    job_repo = cost_setup["job_repo"]
    job_repo.save(cost_setup["job_factory"]("job-1", provider="gemini", model="gemini-2.0"))
    job_repo.save(cost_setup["job_factory"]("job-2", provider="openai", model="gpt-4o"))

    result = cost_setup["svc"].build(
        _filters(
            inventory_id=cost_setup["inv"].id,
            provider_name="openai",
            model_name="gpt-4o",
        )
    )
    assert result.totals.jobs_total == 1
    assert result.totals.total_cost == Decimal("2.00000000")


def test_finished_at_outside_range_excluded(cost_setup) -> None:
    job_repo = cost_setup["job_repo"]
    job_repo.save(
        cost_setup["job_factory"](
            "job-old",
            finished=_utc() - timedelta(days=60),
        )
    )
    result = cost_setup["svc"].build(_filters(inventory_id=cost_setup["inv"].id))
    assert result.totals.jobs_total == 0
    assert result.totals.total_cost is None
