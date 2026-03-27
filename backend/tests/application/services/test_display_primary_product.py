"""select_display_primary_product — stable v3 display rule."""

from datetime import datetime, timezone

from src.application.services.display_primary_product import select_display_primary_product
from src.domain.products.entities import ProductRecord

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)


def test_select_primary_empty() -> None:
    assert select_display_primary_product([]) is None


def test_select_primary_earliest_created_at() -> None:
    older = ProductRecord(
        id="a",
        position_id="p",
        sku="S",
        description="",
        detected_quantity=1,
        confidence=0.9,
        created_at=NOW,
        updated_at=NOW,
        qty_source="manual_review",
    )
    newer = ProductRecord(
        id="b",
        position_id="p",
        sku="S",
        description="",
        detected_quantity=2,
        confidence=0.9,
        created_at=LATER,
        updated_at=LATER,
        qty_source="detected",
    )
    primary = select_display_primary_product([newer, older])
    assert primary is not None
    assert primary.id == "a"
    assert primary.qty_source == "manual_review"


def test_select_primary_tie_breaker_id() -> None:
    a = ProductRecord(
        id="zzz",
        position_id="p",
        sku="S",
        description="",
        detected_quantity=1,
        confidence=0.9,
        created_at=NOW,
        updated_at=NOW,
    )
    b = ProductRecord(
        id="aaa",
        position_id="p",
        sku="S",
        description="",
        detected_quantity=2,
        confidence=0.9,
        created_at=NOW,
        updated_at=NOW,
    )
    primary = select_display_primary_product([a, b])
    assert primary is not None
    assert primary.id == "aaa"
