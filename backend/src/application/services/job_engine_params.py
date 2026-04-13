"""Optional tuning flags read from ``inventory_jobs.engine_params_json`` (comparison / experiments)."""

from __future__ import annotations

from typing import Any


def coerce_prompt_parity_mode(engine_params_json: Any) -> bool:
    """
    When true, hybrid base prompts use **default** branch for OpenAI (same as Gemini/Claude/DeepSeek).

    Accepts JSON-friendly values: boolean, ``\"true\"`` / ``\"1\"`` / ``\"yes\"`` / ``\"on\"`` (case-insensitive),
    or non-zero numbers. Missing or invalid values default to false (production behavior).
    """
    if not isinstance(engine_params_json, dict):
        return False
    v = engine_params_json.get("prompt_parity_mode")
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(v, (int, float)):
        return v != 0
    return False
