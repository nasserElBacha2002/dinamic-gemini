"""
ListAislePositions use case — v3.0 Épica 6.

Returns SKU-level consolidated positions for an aisle with filters, **post-consolidation**
sorting and pagination, and honest metadata when the raw fetch cap is hit (Sprint 1.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import AisleRepository, InventoryRepository, PositionRepository
from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.domain.positions.entities import Position


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
    """Post-consolidation: created_at | updated_at | confidence | sku | quantity"""
    sort_dir: str = "asc"


@dataclass(frozen=True)
class ListAislePositionsResult:
    positions: tuple[Position, ...]
    total_items: int
    page: int
    page_size: int
    raw_fetch_truncated: bool


def _position_quantity(pos: Position) -> int:
    data = pos.detected_summary_json if isinstance(pos.detected_summary_json, dict) else {}
    raw = data.get("final_quantity")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1
    return max(0, value)


def _canonical_sku_lower(pos: Position) -> str:
    summary = pos.detected_summary_json if isinstance(pos.detected_summary_json, dict) else {}
    raw = summary.get("internal_code")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return ""


def _consolidate_by_sku(positions: Sequence[Position]) -> List[Position]:
    by_key: Dict[Tuple[str, str], List[Position]] = {}
    standalone: List[Position] = []
    for p in positions:
        summary = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
        internal_code_raw = summary.get("internal_code")
        internal_code = internal_code_raw.strip() if isinstance(internal_code_raw, str) else None
        if not internal_code:
            standalone.append(p)
            continue
        key = (p.aisle_id, internal_code)
        by_key.setdefault(key, []).append(p)

    consolidated: List[Position] = []

    for (_aisle_id, _sku), group in by_key.items():
        if len(group) == 1:
            consolidated.append(group[0])
            continue

        total_qty = sum(_position_quantity(p) for p in group)
        representative = sorted(group, key=lambda p: (p.created_at, p.id))[0]
        summary = representative.detected_summary_json if isinstance(
            representative.detected_summary_json, dict
        ) else {}
        summary = dict(summary)

        image_ids: set[str] = set()
        filenames: set[str] = set()
        for p in group:
            s = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
            sid = s.get("source_image_id")
            sof = s.get("source_image_original_filename")
            if isinstance(sid, str) and sid.strip():
                image_ids.add(sid.strip())
            if isinstance(sof, str) and sof.strip():
                filenames.add(sof.strip())

        summary["final_quantity"] = total_qty
        if len(image_ids) > 1:
            summary["source_image_id"] = None
        if len(filenames) > 1:
            summary["source_image_original_filename"] = None
        summary["aggregated_from_ids"] = [p.id for p in group]
        representative.detected_summary_json = summary
        consolidated.append(representative)

    consolidated_sorted = sorted(
        consolidated,
        key=lambda p: (
            p.aisle_id,
            str((p.detected_summary_json or {}).get("internal_code")),
            p.created_at,
            p.id,
        ),
    )
    return [*standalone, *consolidated_sorted]


def _sort_key_tuple(p: Position, sort_by: str) -> Tuple:
    sb = (sort_by or "created_at").strip().lower()
    if sb == "updated_at":
        return (p.updated_at, p.id)
    if sb == "confidence":
        return (p.confidence, p.id)
    if sb == "sku":
        return (_canonical_sku_lower(p), p.id)
    if sb == "quantity":
        return (_position_quantity(p), p.id)
    # default created_at
    return (p.created_at, p.id)


class ListAislePositionsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        *,
        positions_aisle_raw_cap: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
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

        raw_q = PositionListQuery(
            status=command.status,
            needs_review=command.needs_review,
            min_confidence=command.min_confidence,
            sku_filter=command.sku_filter,
            page=1,
            page_size=self._raw_cap,
            sort_by="created_at",
            sort_dir="asc",
        )
        raw_positions = list(self._position_repo.list_by_aisle_query(command.aisle_id, raw_q))
        raw_truncated = len(raw_positions) >= self._raw_cap

        consolidated = _consolidate_by_sku(raw_positions)
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
        )
