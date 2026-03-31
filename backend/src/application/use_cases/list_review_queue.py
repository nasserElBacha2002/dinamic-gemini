"""
Cross-inventory review queue — primarily ``needs_review`` positions, narrowable by filters (Sprint 1.4 / 4.2).

Uses existing repositories only (batch ``list_by_aisles``). Suitable for small/medium
deployments; very large multi-inventory installs may need a dedicated SQL path later.
"""

from __future__ import annotations

from datetime import timezone
from typing import Dict, List, Optional, Tuple

from src.application.ports.contracts import (
    ReviewQueueListRow,
    ReviewQueueQuery,
    ReviewQueueSummary,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.display_primary_product import select_display_primary_product
from src.application.utils.review_queue_derived import (
    LOW_CONFIDENCE_THRESHOLD,
    position_has_primary_evidence,
    priority_tier,
    summary_sku_and_detected_quantity,
    traceability_normalized,
    updated_at_sort_ts,
)
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord


def _sort_key(
    row: ReviewQueueListRow,
    sort_by: str,
    sort_dir: str,
    primary_product: Optional[ProductRecord],
) -> tuple:
    """Sort key with reverse=False on list.sort: negate numeric primary key when desc."""
    p = row.position
    sb = (sort_by or "priority").strip().lower()
    desc = (sort_dir or "desc").strip().lower() == "desc"
    if sb == "priority":
        tier = priority_tier(p, primary_product)
        ts = updated_at_sort_ts(p)
        # Tier ascending (P1 first); within tier, newer first (operational queue default).
        return (tier, -ts, p.id)
    if sb == "created_at":
        ct = p.created_at
        ts = ct.timestamp() if ct.tzinfo else ct.replace(tzinfo=timezone.utc).timestamp()
        return (-ts if desc else ts, p.id)
    if sb == "confidence":
        c = p.confidence
        return (-c if desc else c, p.id)
    ts = updated_at_sort_ts(p)
    return (-ts if desc else ts, p.id)


def _position_status_matches(p: Position, raw: Optional[str]) -> bool:
    if raw is None or str(raw).strip() == "":
        return True
    fv = str(raw).strip().lower()
    st = p.status
    if fv == "confirmed":
        return st in (PositionStatus.REVIEWED, PositionStatus.CORRECTED)
    if fv == "detected":
        return st == PositionStatus.DETECTED
    if fv == "reviewed":
        return st == PositionStatus.REVIEWED
    if fv == "corrected":
        return st == PositionStatus.CORRECTED
    if fv == "deleted":
        return st == PositionStatus.DELETED
    return True


def _row_matches_query(
    p: Position,
    q: ReviewQueueQuery,
    primary_product: Optional[ProductRecord],
) -> bool:
    if q.min_confidence is not None and p.confidence < q.min_confidence:
        return False
    if q.max_confidence is not None and p.confidence > q.max_confidence:
        return False
    if not _position_status_matches(p, q.position_status):
        return False

    if q.traceability is not None and str(q.traceability).strip() != "":
        want = str(q.traceability).strip().lower()
        got = traceability_normalized(p, primary_product)
        if want != got:
            return False

    if q.has_evidence is not None:
        has_ev = position_has_primary_evidence(p)
        if q.has_evidence != has_ev:
            return False

    _, qty = summary_sku_and_detected_quantity(p, primary_product)
    if q.qty_zero is not None:
        is_zero = qty == 0
        if q.qty_zero != is_zero:
            return False

    if q.sku_contains is not None and str(q.sku_contains).strip() != "":
        needle = str(q.sku_contains).strip().lower()
        sku, _ = summary_sku_and_detected_quantity(p, primary_product)
        sku_l = (sku or "").lower()
        if needle not in sku_l:
            return False

    return True


def _build_summary(
    rows: List[ReviewQueueListRow],
    primary_by_position: Dict[str, Optional[ProductRecord]],
) -> ReviewQueueSummary:
    pending = len(rows)
    low_conf = 0
    invalid_tr = 0
    qty_z = 0
    missing_ev = 0
    for r in rows:
        p = r.position
        primary = primary_by_position.get(p.id)
        if p.confidence < LOW_CONFIDENCE_THRESHOLD:
            low_conf += 1
        if traceability_normalized(p, primary) == "invalid":
            invalid_tr += 1
        _, qty = summary_sku_and_detected_quantity(p, primary)
        if qty == 0:
            qty_z += 1
        if not position_has_primary_evidence(p):
            missing_ev += 1
    return ReviewQueueSummary(
        pending_review=pending,
        low_confidence=low_conf,
        invalid_traceability=invalid_tr,
        qty_zero=qty_z,
        missing_evidence=missing_ev,
    )


class ListReviewQueueUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo

    def execute(
        self, query: Optional[ReviewQueueQuery] = None
    ) -> Tuple[List[ReviewQueueListRow], int, ReviewQueueSummary]:
        q = query or ReviewQueueQuery()
        scope: List[tuple] = []
        for inv in self._inventory_repo.list_all():
            if q.inventory_id is not None and str(q.inventory_id).strip() and inv.id != q.inventory_id:
                continue
            for aisle in self._aisle_repo.list_by_inventory(inv.id):
                if q.aisle_id is not None and str(q.aisle_id).strip() and aisle.id != q.aisle_id:
                    continue
                scope.append((inv, aisle))

        if not scope:
            empty = ReviewQueueSummary(
                pending_review=0,
                low_confidence=0,
                invalid_traceability=0,
                qty_zero=0,
                missing_evidence=0,
            )
            return [], 0, empty

        aisle_ids = [a.id for _, a in scope]
        by_aisle_id = {a.id: (inv, a) for inv, a in scope}
        positions = list(self._position_repo.list_by_aisles(aisle_ids))
        primary_by_position: Dict[str, Optional[ProductRecord]] = {
            p.id: select_display_primary_product(self._product_record_repo.list_by_position(p.id))
            for p in positions
        }
        pending = [p for p in positions if p.needs_review]
        pending = [p for p in pending if _row_matches_query(p, q, primary_by_position.get(p.id))]

        rows: List[ReviewQueueListRow] = []
        for p in pending:
            inv, aisle = by_aisle_id[p.aisle_id]
            rows.append(
                ReviewQueueListRow(
                    position=p,
                    inventory_id=inv.id,
                    inventory_name=inv.name,
                    aisle_code=aisle.code,
                )
            )

        sb = (q.sort_by or "priority").strip().lower()
        rows.sort(
            key=lambda r: _sort_key(
                r,
                sb,
                q.sort_dir,
                primary_by_position.get(r.position.id),
            ),
            reverse=False,
        )

        summary = _build_summary(rows, primary_by_position)
        total = len(rows)
        page = max(1, q.page)
        page_size = max(1, min(q.page_size, 200))
        start = (page - 1) * page_size
        return rows[start : start + page_size], total, summary
