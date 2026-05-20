"""Aggregate match status for grouped code scan summary rows."""

from __future__ import annotations

from collections import Counter

from src.domain.code_scans.entities import CodeScanDetection


def aggregate_group_match(
    detections: list[CodeScanDetection],
) -> tuple[str | None, tuple[str, ...], tuple[str, ...], dict[str, int] | None]:
    """Return (match_status, matched_position_ids, match_types, match_status_counts)."""
    statuses = [
        d.match_status
        for d in detections
        if d.match_status
    ]
    if not statuses:
        return None, (), (), None

    counts = Counter(statuses)
    if len(counts) == 1:
        status = next(iter(counts))
    else:
        status = "mixed"

    position_ids: list[str] = []
    match_types: list[str] = []
    for d in detections:
        if d.matched_position_id and d.matched_position_id not in position_ids:
            position_ids.append(d.matched_position_id)
        if d.match_type and d.match_type not in match_types:
            match_types.append(d.match_type)

    counts_out: dict[str, int] | None = dict(counts) if status == "mixed" else None
    return status, tuple(position_ids), tuple(match_types), counts_out
