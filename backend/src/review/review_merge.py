"""Stage 2.1.E — Merge report with reviews and recompute summary."""

from typing import Any

ACTIONS = ("SET_COUNT", "MARK_EMPTY", "MARK_INVALID")


def _summary_from_entity_dicts(entities: list[dict[str, Any]]) -> dict[str, int]:
    """Recompute summary from list of entity dicts (with count_status, entity_type)."""
    summary = {
        "total_entities": len(entities),
        "pallets": 0,
        "empty_pallets": 0,
        "loose_boxes": 0,
        "counted": 0,
        "needs_review": 0,
        "not_countable": 0,
        "invalid_structure": 0,
        "counted_manual": 0,
    }
    for e in entities:
        et = e.get("entity_type") or ""
        cs = e.get("count_status") or ""
        if et == "PALLET":
            summary["pallets"] += 1
        elif et == "EMPTY_PALLET":
            summary["empty_pallets"] += 1
        elif et == "LOOSE_BOXES":
            summary["loose_boxes"] += 1
        if cs == "COUNTED":
            summary["counted"] += 1
        elif cs == "COUNTED_MANUAL":
            summary["counted_manual"] += 1
        elif cs == "NEEDS_REVIEW":
            summary["needs_review"] += 1
        elif cs == "NOT_COUNTABLE":
            summary["not_countable"] += 1
        elif cs == "EMPTY":
            pass
        elif cs == "INVALID_STRUCTURE":
            summary["invalid_structure"] += 1
    return summary


def _apply_event_to_entity(entity: dict[str, Any], event: dict[str, Any]) -> None:
    """Mutate entity with after state from event."""
    after = event.get("after")
    if not isinstance(after, dict):
        return
    if "count_status" in after:
        entity["count_status"] = after["count_status"]
    if "final_quantity" in after:
        entity["final_quantity"] = after["final_quantity"]


def merge_resolved_report(report: dict[str, Any], reviews: dict[str, Any]) -> dict[str, Any]:
    """Merge review overrides into report and recompute summary. Does not mutate report.

    reviews: dict from load_reviews (entity_uid -> { entity_uid, events }).
    Latest event per entity wins. Actions: SET_COUNT (COUNTED_MANUAL + final_quantity),
    MARK_EMPTY (EMPTY, 0), MARK_INVALID (INVALID_STRUCTURE).
    """
    report = dict(report)
    entities = list(report.get("entities") or [])
    report["entities"] = entities
    entity_by_uid: dict[str, dict[str, Any]] = {
        e.get("entity_uid"): e for e in entities if e.get("entity_uid")
    }

    for entity_uid, rec in (reviews or {}).items():
        if not isinstance(rec, dict):
            continue
        events = rec.get("events")
        if not isinstance(events, list) or not events:
            continue
        ent = entity_by_uid.get(entity_uid)
        if ent is None:
            continue
        last = events[-1]
        _apply_event_to_entity(ent, last)

    report["summary"] = _summary_from_entity_dicts(entities)
    return report
