"""
SKU-level position consolidation for v3 aisle results / export.

Same algorithm as historical ``ListAislePositionsUseCase`` consolidation: group by
(``aisle_id``, ``internal_code`` from ``detected_summary_json``), sum quantities into
representative row, attach ``aggregated_from_ids``.

Sprint 4 note: this remains a projection-time technical mutation on the representative snapshot.
It does not by itself establish a new persisted source of truth for aggregated rows.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from src.domain.positions.entities import Position


def position_quantity_from_summary(pos: Position) -> int:
    data = pos.detected_summary_json if isinstance(pos.detected_summary_json, dict) else {}
    raw = data.get("final_quantity")
    if raw is None:
        return 1
    if isinstance(raw, bool):
        return 1
    if isinstance(raw, int):
        return max(0, raw)
    if isinstance(raw, str):
        try:
            return max(0, int(raw.strip(), 10))
        except (TypeError, ValueError):
            return 1
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 1


def canonical_internal_code_lower(pos: Position) -> str:
    summary = pos.detected_summary_json if isinstance(pos.detected_summary_json, dict) else {}
    raw = summary.get("internal_code")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return ""


def consolidate_positions_by_sku(
    positions: Sequence[Position],
    *,
    enabled: bool = True,
) -> List[Position]:
    """Merge raw positions with the same aisle + SKU into one representative row (in-place summary update).

    When ``enabled`` is False, returns raw positions in list order (no merge) — used for photo-focused
    aisle review so rows stay one-to-one with detections.
    """
    if not enabled:
        return list(positions)
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

        total_qty = sum(position_quantity_from_summary(p) for p in group)
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
