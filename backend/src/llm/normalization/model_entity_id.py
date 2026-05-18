"""
Repair missing or duplicate ``model_entity_id`` values before strict v2.1 schema validation.

``model_entity_id`` is a technical identifier (not business evidence). OpenAI ``json_object``
responses may omit it or return null; Gemini structured output is stricter.
"""

from __future__ import annotations

import copy
from typing import Any


def _is_non_empty_model_entity_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _allocate_unique_model_entity_id(used: set[str], preferred: str | None = None) -> str:
    if preferred is not None and preferred not in used:
        return preferred
    n = 1
    while True:
        candidate = f"E{n}"
        n += 1
        if candidate not in used:
            return candidate


def normalize_model_entity_ids(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Ensure each entity has a unique non-empty ``model_entity_id`` (``E1``, ``E2``, …).

    Mutates a deep copy of ``data`` (and nested entity dicts). Returns repair diagnostic messages.
    """
    out = copy.deepcopy(data)
    warnings: list[str] = []
    entities = out.get("entities")
    if not isinstance(entities, list):
        return out, warnings

    used: set[str] = set()
    for i, ent in enumerate(entities):
        if not isinstance(ent, dict):
            continue
        raw = ent.get("model_entity_id")
        if not _is_non_empty_model_entity_id(raw):
            preferred = f"E{i + 1}"
            new_id = _allocate_unique_model_entity_id(used, preferred)
            ent["model_entity_id"] = new_id
            warnings.append(f"model_entity_id missing for entity index {i}; generated {new_id}")
            used.add(new_id)
            continue

        mid = str(raw).strip()
        if mid in used:
            new_id = _allocate_unique_model_entity_id(used)
            ent["model_entity_id"] = new_id
            warnings.append(f"model_entity_id duplicated at entity index {i}; generated {new_id}")
            used.add(new_id)
        else:
            ent["model_entity_id"] = mid
            used.add(mid)

    return out, warnings
