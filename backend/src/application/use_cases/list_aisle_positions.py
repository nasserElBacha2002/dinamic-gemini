"""
ListAislePositions use case — v3.0 Épica 6.

Returns positions for an aisle with optional filters and pagination.
Fails if inventory or aisle does not exist or aisle does not belong to inventory.
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
    query: Optional[PositionListQuery] = None


class ListAislePositionsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo

    def execute(self, command: ListAislePositionsCommand) -> Sequence[Position]:
        """
        v3.2.3: Returns SKU-level consolidated positions for an aisle.

        Semantics:
        - Same aisle + same canonical SKU ("internal_code") are aggregated into a single
          logical position row.
        - Quantity per SKU is the sum of per-position final_quantity values when present,
          falling back to 1 when missing.
        - Positions without a canonical SKU are never aggregated and remain as-is.
        - When multiple physical positions contribute to a SKU aggregate:
          - We keep one representative Position instance.
          - Its detected_summary_json["final_quantity"] is updated to the aggregated sum.
          - If more than one distinct source image id / filename is present in the group,
            the representative's source_image_id and source_image_original_filename are
            cleared from detected_summary_json so that the API layer does not expose
            a misleading single-image reference.
          - For auditability, the representative summary gains an "aggregated_from_ids"
            list with all contributing position ids (including the representative).
        """
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
        # Always use list_by_aisle_query so pagination and filters share one path (§9.7).
        # When command.query is omitted, default PositionListQuery() matches former list_by_aisle defaults (page=1, page_size=25).
        q = command.query if command.query is not None else PositionListQuery()
        positions = list(self._position_repo.list_by_aisle_query(command.aisle_id, q))

        # Group by (aisle_id, canonical SKU). Positions without a valid internal_code
        # are emitted as-is and never merged.
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

        # Helper to read per-position quantity from detected_summary_json.
        def _position_quantity(pos: Position) -> int:
            data = pos.detected_summary_json if isinstance(pos.detected_summary_json, dict) else {}
            raw = data.get("final_quantity")
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return 1
            return max(0, value)

        for (_aisle_id, _sku), group in by_key.items():
            if len(group) == 1:
                # Single position for this SKU → no aggregation needed; keep as-is.
                consolidated.append(group[0])
                continue

            # Multiple positions for the same SKU in the same aisle.
            # Aggregate quantity and normalise metadata on the representative.
            total_qty = sum(_position_quantity(p) for p in group)

            # Choose a representative deterministically: earliest created_at, then id.
            representative = sorted(group, key=lambda p: (p.created_at, p.id))[0]
            summary = representative.detected_summary_json if isinstance(
                representative.detected_summary_json, dict
            ) else {}
            summary = dict(summary)  # shallow copy to avoid mutating shared dicts

            # Collect distinct source image ids / filenames across the group.
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

            # Update final_quantity to reflect the aggregated SKU quantity.
            summary["final_quantity"] = total_qty

            # When multiple source images / filenames contribute, clear them so the
            # API does not expose a misleading single-image reference.
            if len(image_ids) > 1:
                summary["source_image_id"] = None
            if len(filenames) > 1:
                summary["source_image_original_filename"] = None

            # Attach provenance for auditability.
            summary["aggregated_from_ids"] = [p.id for p in group]

            representative.detected_summary_json = summary
            consolidated.append(representative)

        # Emit standalone (no-SKU) positions and consolidated SKU aggregates.
        # Preserve a stable ordering: standalone first in original order, then
        # aggregates ordered by (aisle_id, sku, created_at, id).
        consolidated_sorted = sorted(
            consolidated,
            key=lambda p: (p.aisle_id, str(
                (p.detected_summary_json or {}).get("internal_code")
            ), p.created_at, p.id),
        )
        return [*standalone, *consolidated_sorted]
