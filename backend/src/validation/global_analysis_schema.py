"""
Stage 3 — Strict structural validation for global analysis response.

Validates required keys, types, and constraints. Does not auto-correct.
"""

from typing import Any, Dict

from src.exceptions.global_analysis_exceptions import GlobalAnalysisValidationError


def validate_global_analysis_structure(data: Dict[str, Any]) -> None:
    """Validate that data conforms to the global analysis response schema.

    Checks:
    - Root keys: total_pallets_detected, pallets.
    - pallets is a list.
    - Each pallet has pallet_id (str), has_label (bool), confidence (float).
    - confidence in [0, 1].
    - total_pallets_detected == len(pallets).

    Extra root keys are allowed and ignored.

    Args:
        data: Parsed JSON dict from Gemini response.

    Raises:
        GlobalAnalysisValidationError: If any structural check fails.
    """
    if not isinstance(data, dict):
        raise GlobalAnalysisValidationError("Response must be a JSON object")

    if "total_pallets_detected" not in data:
        raise GlobalAnalysisValidationError("Missing required key: total_pallets_detected")
    if "pallets" not in data:
        raise GlobalAnalysisValidationError("Missing required key: pallets")

    total = data["total_pallets_detected"]
    pallets = data["pallets"]

    if not isinstance(pallets, list):
        raise GlobalAnalysisValidationError("'pallets' must be a list")

    if total != len(pallets):
        raise GlobalAnalysisValidationError(
            f"total_pallets_detected ({total}) must equal len(pallets) ({len(pallets)})"
        )

    for i, p in enumerate(pallets):
        if not isinstance(p, dict):
            raise GlobalAnalysisValidationError(f"pallets[{i}] must be an object")
        if "pallet_id" not in p:
            raise GlobalAnalysisValidationError(f"pallets[{i}] missing 'pallet_id'")
        if not isinstance(p["pallet_id"], str):
            raise GlobalAnalysisValidationError(f"pallets[{i}].pallet_id must be a string")
        if "has_label" not in p:
            raise GlobalAnalysisValidationError(f"pallets[{i}] missing 'has_label'")
        if not isinstance(p["has_label"], bool):
            raise GlobalAnalysisValidationError(f"pallets[{i}].has_label must be a boolean")
        if "confidence" not in p:
            raise GlobalAnalysisValidationError(f"pallets[{i}] missing 'confidence'")
        try:
            c = float(p["confidence"])
        except (TypeError, ValueError):
            raise GlobalAnalysisValidationError(
                f"pallets[{i}].confidence must be a number, got {type(p['confidence']).__name__!r}"
            )
        if not (0 <= c <= 1):
            raise GlobalAnalysisValidationError(
                f"pallets[{i}].confidence must be in [0, 1], got {c}"
            )


# --- v2.1 Entity schema ---

ENTITY_TYPES_V21 = frozenset({"PALLET", "EMPTY_PALLET", "LOOSE_BOXES"})


def _check_bbox(obj: Any, key: str, prefix: str) -> None:
    """Raise if key is present and not a valid normalized [x1,y1,x2,y2]: len 4, 0<=x<=1, x1<x2, y1<y2. Allow null."""
    val = obj.get(key)
    if val is None:
        return
    if not isinstance(val, list) or len(val) != 4:
        raise GlobalAnalysisValidationError(
            f"{prefix}.{key} must be null or [x1,y1,x2,y2] (length 4), got {type(val).__name__!r}"
        )
    nums = []
    for j, v in enumerate(val):
        if not isinstance(v, (int, float)):
            raise GlobalAnalysisValidationError(
                f"{prefix}.{key}[{j}] must be numeric, got {type(v).__name__!r}"
            )
        n = float(v)
        if not (0 <= n <= 1):
            raise GlobalAnalysisValidationError(
                f"{prefix}.{key}[{j}] must be in [0, 1] (normalized), got {n}"
            )
        nums.append(n)
    x1, y1, x2, y2 = nums
    if x1 >= x2:
        raise GlobalAnalysisValidationError(
            f"{prefix}.{key} must have x1 < x2, got x1={x1}, x2={x2}"
        )
    if y1 >= y2:
        raise GlobalAnalysisValidationError(
            f"{prefix}.{key} must have y1 < y2, got y1={y1}, y2={y2}"
        )


def validate_global_analysis_structure_v21(data: Dict[str, Any]) -> None:
    """Validate that data conforms to the v2.1 global analysis response schema.

    Checks:
    - Root keys: total_entities_detected, entities.
    - entities is a list.
    - Each entity has entity_type in {PALLET, EMPTY_PALLET, LOOSE_BOXES}, model_entity_id (unique), confidence in [0,1].
    - product_label_quantity is int or null.
    - position_label_bbox / product_label_bbox if present are [x1,y1,x2,y2] or null.
    - total_entities_detected == len(entities).

    Args:
        data: Parsed JSON dict from Gemini v2.1 response.

    Raises:
        GlobalAnalysisValidationError: If any structural check fails.
    """
    if not isinstance(data, dict):
        raise GlobalAnalysisValidationError("Response must be a JSON object")

    if "total_entities_detected" not in data:
        raise GlobalAnalysisValidationError("Missing required key: total_entities_detected")
    if "entities" not in data:
        raise GlobalAnalysisValidationError("Missing required key: entities")

    total = data["total_entities_detected"]
    entities = data["entities"]

    if not isinstance(total, int) or total < 0:
        raise GlobalAnalysisValidationError(
            "total_entities_detected must be a non-negative integer"
        )
    if not isinstance(entities, list):
        raise GlobalAnalysisValidationError("'entities' must be a list")

    if total != len(entities):
        raise GlobalAnalysisValidationError(
            f"total_entities_detected ({total}) must equal len(entities) ({len(entities)})"
        )

    seen_model_ids = set()
    for i, e in enumerate(entities):
        if not isinstance(e, dict):
            raise GlobalAnalysisValidationError(f"entities[{i}] must be an object")
        prefix = f"entities[{i}]"

        if "entity_type" not in e:
            raise GlobalAnalysisValidationError(f"{prefix} missing 'entity_type'")
        et = e.get("entity_type")
        if et not in ENTITY_TYPES_V21:
            raise GlobalAnalysisValidationError(
                f"{prefix}.entity_type must be one of {sorted(ENTITY_TYPES_V21)}, got {et!r}"
            )

        if "model_entity_id" not in e:
            raise GlobalAnalysisValidationError(f"{prefix} missing 'model_entity_id'")
        mid = e.get("model_entity_id")
        if not isinstance(mid, str):
            raise GlobalAnalysisValidationError(
                f"{prefix}.model_entity_id must be a string, got {type(mid).__name__!r}"
            )
        if mid in seen_model_ids:
            raise GlobalAnalysisValidationError(
                f"Duplicate model_entity_id: {mid!r}"
            )
        seen_model_ids.add(mid)

        if "confidence" not in e:
            raise GlobalAnalysisValidationError(f"{prefix} missing 'confidence'")
        try:
            c = float(e["confidence"])
        except (TypeError, ValueError):
            raise GlobalAnalysisValidationError(
                f"{prefix}.confidence must be a number, got {type(e['confidence']).__name__!r}"
            )
        if not (0 <= c <= 1):
            raise GlobalAnalysisValidationError(
                f"{prefix}.confidence must be in [0, 1], got {c}"
            )

        qty = e.get("product_label_quantity")
        if qty is not None:
            if not isinstance(qty, int):
                try:
                    int(qty)
                except (TypeError, ValueError):
                    raise GlobalAnalysisValidationError(
                        f"{prefix}.product_label_quantity must be int or null, got {type(qty).__name__!r}"
                    )

        if "has_boxes" not in e:
            raise GlobalAnalysisValidationError(f"{prefix} missing 'has_boxes'")
        if not isinstance(e["has_boxes"], bool):
            raise GlobalAnalysisValidationError(
                f"{prefix}.has_boxes must be a boolean"
            )

        _check_bbox(e, "position_label_bbox", prefix)
        _check_bbox(e, "product_label_bbox", prefix)
        _check_bbox(e, "extent_bbox", prefix)
