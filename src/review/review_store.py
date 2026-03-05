"""Stage 2.1.E — Review store (filesystem MVP). run/reviews.json per job."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REVIEWS_FILENAME = "reviews.json"


def _reviews_path(run_dir: Path) -> Path:
    return run_dir / REVIEWS_FILENAME


def load_reviews(run_dir: Path) -> Dict[str, Any]:
    """Load reviews from run_dir/reviews.json. Returns dict keyed by entity_uid with events list."""
    path = _reviews_path(run_dir)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load reviews from %s: %s", path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_review(
    run_dir: Path,
    entity_uid: str,
    review_event: Dict[str, Any],
) -> None:
    """Append a review event for entity_uid. Creates/updates run_dir/reviews.json."""
    path = _reviews_path(run_dir)
    data = load_reviews(run_dir)
    if entity_uid not in data:
        data[entity_uid] = {"entity_uid": entity_uid, "events": []}
    data[entity_uid].setdefault("events", []).append(review_event)
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_reviews(run_dir: Path) -> Dict[str, Any]:
    """Return full reviews structure (entity_uid -> { entity_uid, events })."""
    return load_reviews(run_dir)


def get_entity_audit(job_id: str, run_dir: Path, entity_uid: str) -> List[Dict[str, Any]]:
    """Return audit events for entity_uid. Empty list if none."""
    data = load_reviews(run_dir)
    ent = data.get(entity_uid)
    if not ent or not isinstance(ent, dict):
        return []
    events = ent.get("events")
    return list(events) if isinstance(events, list) else []
