"""Group enriched results by published aisle position (Phase 5)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from src.application.services.position_reconciliation.published_assignment_read_model import (
    PublishedPositionAssignmentView,
)


@dataclass(frozen=True)
class PositionGroupBucket:
    position_id: str | None
    position_name: str | None
    label: str
    product_count: int
    total_quantity: int
    items: tuple[Any, ...]


def group_summaries_by_position(
    summaries: list[Any],
    *,
    views_by_result_id: dict[str, PublishedPositionAssignmentView],
    primary_product_ids: list[str | None],
    unassigned_label: str = "Sin posición",
) -> list[PositionGroupBucket]:
    """Group already-enriched summaries by published position name.

    ``primary_product_ids`` must align 1:1 with ``summaries``.
    Unassigned / missing views share the null group; never hide that group when empty of names.
    """
    buckets: dict[tuple[str | None, str | None], list[Any]] = defaultdict(list)
    qty_by_key: dict[tuple[str | None, str | None], int] = defaultdict(int)

    for summary, product_id in zip(summaries, primary_product_ids):
        view = views_by_result_id.get(product_id) if product_id else None
        name = view.position.name if view and view.position else None
        label_id = view.position.id if view and view.position else None
        key: tuple[str | None, str | None]
        if name:
            key = (label_id, name)
        else:
            key = (None, None)
        buckets[key].append(summary)
        final_qty = getattr(getattr(summary, "quantity", None), "final", None)
        if final_qty is None:
            final_qty = getattr(summary, "qty", 0) or 0
        try:
            qty_by_key[key] += int(final_qty)
        except (TypeError, ValueError):
            pass

    groups: list[PositionGroupBucket] = []
    # Named positions first (stable by name), then unassigned.
    named_keys = sorted(
        (k for k in buckets if k[1] is not None),
        key=lambda k: (k[1] or "").lower(),
    )
    for key in named_keys:
        items = tuple(buckets[key])
        groups.append(
            PositionGroupBucket(
                position_id=key[0],
                position_name=key[1],
                label=key[1] or unassigned_label,
                product_count=len(items),
                total_quantity=qty_by_key[key],
                items=items,
            )
        )
    unassigned_key = (None, None)
    if unassigned_key in buckets or not groups:
        items = tuple(buckets.get(unassigned_key, ()))
        groups.append(
            PositionGroupBucket(
                position_id=None,
                position_name=None,
                label=unassigned_label,
                product_count=len(items),
                total_quantity=qty_by_key.get(unassigned_key, 0),
                items=items,
            )
        )
    return groups
