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
