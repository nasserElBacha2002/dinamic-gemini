"""
ListAislePositions use case — v3.0 Épica 6.

Returns positions for an aisle with filters, optional SKU consolidation, **post-merge** sorting
and pagination, and honest metadata when the raw fetch cap is hit (Sprint 1.4).

Phase 2: raw rows are limited to one result context (**explicit** ``job_id`` → **operational_job_id**
→ **legacy** ``job_id IS NULL`` only). There is no implicit latest-job fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import AisleRepository, InventoryRepository, PositionRepository
from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.services.position_sku_consolidation import (
    canonical_internal_code_lower,
    consolidate_positions_by_sku,
    position_quantity_from_summary,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.domain.positions.entities import Position

logger = logging.getLogger(__name__)


@dataclass
class ListAislePositionsCommand:
    inventory_id: str
    aisle_id: str
    status: Optional[str] = None
    needs_review: Optional[bool] = None
    min_confidence: Optional[float] = None
    sku_filter: Optional[str] = None
    page: int = 1
    page_size: int = 25
    sort_by: str = "created_at"
    """Post-consolidation: created_at | updated_at | confidence | sku | quantity | photo_sequence"""
    sort_dir: str = "asc"
    #: Optional override; omitted uses Result Context Resolver (operational / legacy).
    job_id: Optional[str] = None
    #: When False, skip SKU merge (photo-accurate review rows). Ignored when ``sort_by`` is
    #: ``photo_sequence`` (merge is always off for that mode).
    consolidate_by_sku: bool = True


@dataclass(frozen=True)
class ListAislePositionsResult:
    positions: tuple[Position, ...]
    total_items: int
    page: int
    page_size: int
    raw_fetch_truncated: bool
    resolved_job_id: Optional[str]
    """Effective slice: ``None`` = legacy null-job rows."""
    result_context_source: str
    """explicit | operational | legacy"""


def _sort_key_tuple(p: Position, sort_by: str) -> Tuple:
    sb = (sort_by or "created_at").strip().lower()
    if sb == "updated_at":
        return (p.updated_at, p.id)
    if sb == "confidence":
        return (p.confidence, p.id)
    if sb == "sku":
        return (canonical_internal_code_lower(p), p.id)
    if sb == "quantity":
        return (position_quantity_from_summary(p), p.id)
    if sb == "photo_sequence":
        return _photo_review_sort_key(p)
    # default created_at
    return (p.created_at, p.id)


def _photo_review_sort_key(p: Position) -> Tuple[Any, ...]:
    """Stable order: manifest photo sequence, then filename, image id, position code, id."""
    s = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    raw_seq = s.get("source_image_sequence")
    try:
        seq_v = int(raw_seq) if raw_seq is not None else 1_000_000
    except (TypeError, ValueError):
        seq_v = 1_000_000
    fn = s.get("source_image_original_filename")
    fn_l = fn.lower() if isinstance(fn, str) else ""
    sid = s.get("source_image_id")
    sid_l = sid.lower() if isinstance(sid, str) else ""
    pcode = ""
    for k in ("position_barcode", "pallet_id", "entity_uid"):
        v = s.get(k)
        if isinstance(v, str) and v.strip():
            pcode = v.strip().lower()
            break
    if not pcode:
        pcode = p.id.lower()
    return (seq_v, fn_l, sid_l, pcode, p.id)


class ListAislePositionsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        result_context_resolver: ResultContextResolver,
        *,
        positions_aisle_raw_cap: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._resolver = result_context_resolver
        self._raw_cap = max(1, int(positions_aisle_raw_cap))

    def execute(self, command: ListAislePositionsCommand) -> ListAislePositionsResult:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {command.aisle_id}")
        if aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )

        ctx = self._resolver.resolve(aisle=aisle, explicit_job_id=command.job_id)
        raw_q = PositionListQuery(
            status=command.status,
            needs_review=command.needs_review,
            min_confidence=command.min_confidence,
            sku_filter=command.sku_filter,
            page=1,
            page_size=self._raw_cap,
            sort_by="created_at",
            sort_dir="asc",
            job_id=ctx.job_id_for_slice,
        )
        # Bounded raw load within the resolved job slice only — not an unscoped "all rows in aisle" read.
        raw_positions = list(self._position_repo.list_by_aisle_query(command.aisle_id, raw_q))
        raw_truncated = len(raw_positions) >= self._raw_cap
        logger.info(
            "v3.list_aisle_positions raw_fetch inventory_id=%s aisle_id=%s job_slice=%r "
            "context=%s rows=%d cap=%d truncated=%s",
            command.inventory_id,
            command.aisle_id,
            ctx.job_id_for_slice,
            ctx.source,
            len(raw_positions),
            self._raw_cap,
            raw_truncated,
        )

        sort_key = (command.sort_by or "created_at").strip().lower()
        effective_consolidate = command.consolidate_by_sku
        if sort_key == "photo_sequence" and effective_consolidate:
            logger.info(
                "list_aisle_positions: sort_by=photo_sequence is not compatible with SKU merge; "
                "using consolidate_by_sku=false for this request"
            )
            effective_consolidate = False

        consolidated = consolidate_positions_by_sku(
            raw_positions,
            enabled=effective_consolidate,
        )
        reverse = (command.sort_dir or "asc").strip().lower() == "desc"
        consolidated_sorted = sorted(
            consolidated,
            key=lambda p: _sort_key_tuple(p, command.sort_by),
            reverse=reverse,
        )

        total = len(consolidated_sorted)
        page = max(1, command.page)
        page_size = max(1, command.page_size)
        start = (page - 1) * page_size
        page_rows = consolidated_sorted[start : start + page_size]

        return ListAislePositionsResult(
            positions=tuple(page_rows),
            total_items=total,
            page=page,
            page_size=page_size,
            raw_fetch_truncated=raw_truncated,
            resolved_job_id=ctx.job_id_for_slice,
            result_context_source=ctx.source,
        )
