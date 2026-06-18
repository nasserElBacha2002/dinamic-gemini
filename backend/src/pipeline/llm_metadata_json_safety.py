"""JSON-safety helpers for LLMRequest metadata and run_metadata propagation."""

from __future__ import annotations

import json
from typing import Any

from src.pipeline.execution_log_sanitizer import (
    RUNTIME_METADATA_KEYS,
    find_non_json_serializable_path,
    json_safe_metadata_snapshot,
    make_json_safe_for_execution_log,
)


def strip_runtime_keys_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Remove known runtime-only metadata keys (defensive; prefer not storing them)."""
    return {
        key: value
        for key, value in metadata.items()
        if str(key) not in RUNTIME_METADATA_KEYS
    }


def sanitize_llm_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Return a JSON-serializable metadata dict without runtime provider/image objects."""
    from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_COMPOSITION

    if not metadata:
        return {}
    stripped = strip_runtime_keys_from_metadata(dict(metadata))
    prompt_composition = stripped.get(LLM_METADATA_KEY_PROMPT_COMPOSITION)
    preserve_prompt_composition = (
        isinstance(prompt_composition, dict)
        and find_non_json_serializable_path(prompt_composition) is None
    )
    safe = json_safe_metadata_snapshot(stripped)
    if preserve_prompt_composition and isinstance(safe, dict):
        safe[LLM_METADATA_KEY_PROMPT_COMPOSITION] = prompt_composition
    return safe


def assert_metadata_json_serializable(metadata: dict[str, Any], *, context: str = "metadata") -> None:
    """Raise ValueError with dotted path when metadata is not JSON-serializable."""
    bad_path = find_non_json_serializable_path(metadata)
    if bad_path:
        raise ValueError(
            f"{context} serialization failed at {bad_path}: value is not JSON serializable"
        )
    json.dumps(metadata)


def metadata_contains_runtime_leaks(metadata: dict[str, Any]) -> list[str]:
    """Return dotted paths of redacted runtime object placeholders (for tests)."""
    leaks: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if "__redacted_runtime_object__" in value and path:
                leaks.append(path)
            for key, item in value.items():
                child = f"{path}.{key}" if path else str(key)
                walk(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]" if path else f"[{index}]")

    walk(make_json_safe_for_execution_log(metadata), "")
    return leaks
