"""Phase 5.1 analytics aggregation tests (in-memory)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.application.dto.analytics_dto import AnalyticsFilters
from src.application.services.analytics_aggregation_core import (
    aggregate_settling_metrics,
    day_span_inclusive,
    issue_bucket_for_position,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.reviews.entities import ReviewAction, ReviewActionType
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_review_action_repository import MemoryReviewActionRepository
from src.infrastructure.repositories.memory_analytics_repository import MemoryAnalyticsRepository


def _utc(minutes: int = 0) -> datetime:
    base = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=minutes)


@pytest.fixture
def memory_analytics_setup():
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    rev_repo = MemoryReviewActionRepository()

    inv = Inventory(
        id="inv-1",
        name="Test Inv",
        status=InventoryStatus.DRAFT,
        created_at=_utc(0),
        updated_at=_utc(0),
        completed_at=None,
    )
    inv_repo.save(inv)
    aisle = Aisle(
        id="aisle-1",
        inventory_id=inv.id,
        code="A1",
        status=AisleStatus.PROCESSED,
        created_at=_utc(0),
        updated_at=_utc(0),
    )
    aisle_repo.save(aisle)

    p1 = Position(
        id="pos-1",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id="ev-1",
        created_at=_utc(0),
        updated_at=_utc(5),
        detected_summary_json={"traceability_status": "valid"},
    )
    p2 = Position(
        id="pos-2",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.3,
        needs_review=True,
        primary_evidence_id="ev-2",
        created_at=_utc(0),
        updated_at=_utc(6),
        detected_summary_json={"traceability_status": "invalid"},
    )
    pos_repo.save(p1)
    pos_repo.save(p2)

    ra_confirm = ReviewAction(
        id="ra-1",
        position_id=p1.id,
        action_type=ReviewActionType.CONFIRM,
        before_json={},
        after_json={},
        created_at=_utc(10),
    )
    ra_corr = ReviewAction(
        id="ra-2",
        position_id=p2.id,
        action_type=ReviewActionType.UPDATE_SKU,
        before_json={},
        after_json={},
        created_at=_utc(11),
    )
    rev_repo.save(ra_confirm)
    rev_repo.save(ra_corr)

    analytics = MemoryAnalyticsRepository(inv_repo, aisle_repo, pos_repo, rev_repo)
    return analytics, inv, aisle


def test_aggregate_settling_metrics_counts():
    ra = [
        ReviewAction("a", "p", ReviewActionType.CONFIRM, {}, {}, _utc(0)),
        ReviewAction("b", "p", ReviewActionType.UPDATE_QUANTITY, {}, {}, _utc(1)),
        ReviewAction("c", "p", ReviewActionType.DELETE_POSITION, {}, {}, _utc(2)),
    ]
    s, c, corr = aggregate_settling_metrics(ra, None, None)
    assert s == 2
    assert c == 1
    assert corr == 1


def test_day_span():
    d0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d1 = datetime(2026, 1, 3, tzinfo=timezone.utc)
    assert day_span_inclusive(d0, d1) == 3


def test_issue_bucket_invalid_traceability():
    p = Position(
        id="x",
        aisle_id="a",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id="e",
        created_at=_utc(),
        updated_at=_utc(),
        detected_summary_json={"traceability_status": "invalid"},
    )
    assert issue_bucket_for_position(p) == "invalid_traceability"


def test_memory_summary_rates(memory_analytics_setup):
    analytics, *_ = memory_analytics_setup
    f = AnalyticsFilters(date_from=_utc(-60), date_to=_utc(120), inventory_id=None, aisle_id=None)
    s = analytics.get_summary(f)
    assert s.settling_actions_count == 2
    assert s.auto_acceptance_rate == pytest.approx(0.5)
    assert s.manual_correction_rate == pytest.approx(0.5)
    assert s.invalid_traceability_rate == pytest.approx(0.5)
    assert s.positions_in_scope == 2


def test_memory_quality_patterns(memory_analytics_setup):
    analytics, *_ = memory_analytics_setup
    f = AnalyticsFilters(date_from=None, date_to=None, inventory_id=None, aisle_id=None)
    rows = analytics.get_quality_patterns(f)
    types_found = {r.issue_type for r in rows}
    assert "Invalid traceability" in types_found


def test_memory_empty_data():
    analytics = MemoryAnalyticsRepository(
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryPositionRepository(),
        MemoryReviewActionRepository(),
    )
    s = analytics.get_summary(AnalyticsFilters())
    assert s.positions_in_scope == 0
    assert s.settling_actions_count == 0
    assert s.auto_acceptance_rate is None
