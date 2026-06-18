"""
Defensive JSON sanitization for execution_log payloads and persisted metadata.

Runtime provider/image objects must never be written to execution_log artifacts.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

REDACTED_RUNTIME_OBJECT_KEY = "__redacted_runtime_object__"

# Keys that must never appear in serializable metadata or execution logs.
RUNTIME_METADATA_KEYS = frozenset(
    {
        "_provider_execution_request_object",
        "_serialized_multimodal_payload",
        "provider_execution_request_object",
        "serialized_multimodal_payload",
    }
)


def _type_name(value: Any) -> str:
    return type(value).__name__


def _redact_runtime_object(value: Any, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {REDACTED_RUNTIME_OBJECT_KEY: _type_name(value)}
    if extra:
        out.update(extra)
    return out


def make_json_safe_for_execution_log(
    value: Any,
    *,
    path: str = "",
    _depth: int = 0,
) -> Any:
    """
    Recursively convert a value into a JSON-serializable structure for execution logs.

    Unknown runtime objects are redacted with type/shape hints — never raw bytes or images.
    """
    if _depth > 32:
        return _redact_runtime_object(value, extra={"path": path or "<max_depth>"})

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"

    if isinstance(value, (Path, MappingProxyType)):
        return str(value)

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, (bytes, bytearray, memoryview)):
        return _redact_runtime_object(
            value,
            extra={"byte_length": len(value), "path": path or None},
        )

    # NumPy — optional import; ndarray/scalars are common runtime leaks.
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return _redact_runtime_object(
                value,
                extra={
                    "shape": list(value.shape),
                    "dtype": str(value.dtype),
                    "path": path or None,
                },
            )
        if isinstance(value, np.generic):
            return _redact_runtime_object(
                value,
                extra={"dtype": str(value.dtype), "path": path or None},
            )
    except ImportError:
        pass

    try:
        from PIL import Image

        if isinstance(value, Image.Image):
            return _redact_runtime_object(
                value,
                extra={
                    "mode": value.mode,
                    "size": list(value.size),
                    "path": path or None,
                },
            )
    except ImportError:
        pass

    module_name = getattr(type(value), "__module__", "") or ""
    if module_name.startswith("google.genai"):
        return _redact_runtime_object(value, extra={"path": path or None})

    type_name = _type_name(value)
    if type_name in {
        "ProviderExecutionRequest",
        "SerializedMultimodalPayload",
        "SerializedImagePayloadEntry",
        "ImageRuntimeResource",
        "ProviderExecutionImage",
        "ExecutionImageManifest",
    }:
        return _redact_runtime_object(value, extra={"path": path or None})

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str in RUNTIME_METADATA_KEYS or (
                key_str.startswith("_") and key_str.endswith("_object")
            ):
                out[key_str] = _redact_runtime_object(item, extra={"path": _join_path(path, key_str)})
                continue
            out[key_str] = make_json_safe_for_execution_log(
                item,
                path=_join_path(path, key_str),
                _depth=_depth + 1,
            )
        return out

    if isinstance(value, (list, tuple)):
        return [
            make_json_safe_for_execution_log(
                item,
                path=f"{path}[{index}]" if path else f"[{index}]",
                _depth=_depth + 1,
            )
            for index, item in enumerate(value)
        ]

    if is_dataclass(value):
        return make_json_safe_for_execution_log(
            asdict(value),
            path=path,
            _depth=_depth + 1,
        )

    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return _redact_runtime_object(value, extra={"path": path or None})


def _join_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def find_non_json_serializable_path(
    value: Any,
    *,
    path: str = "",
    _depth: int = 0,
) -> str | None:
    """Return dotted path to first value that cannot be json.dumps'd, or None if safe."""
    if _depth > 32:
        return path or "<max_depth>"

    if value is None or isinstance(value, (bool, str, int, float)):
        return None

    if isinstance(value, (dict, list, tuple)):
        if isinstance(value, dict):
            for key, item in value.items():
                child = _join_path(path, str(key))
                found = find_non_json_serializable_path(item, path=child, _depth=_depth + 1)
                if found:
                    return found
            return None
        for index, item in enumerate(value):
            child = f"{path}[{index}]" if path else f"[{index}]"
            found = find_non_json_serializable_path(item, path=child, _depth=_depth + 1)
            if found:
                return found
        return None

    try:
        json.dumps(value)
        return None
    except (TypeError, ValueError):
        return path or "<root>"


def json_safe_metadata_snapshot(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Produce a JSON-safe copy of LLM/job metadata for logs and persistence guards."""
    if not metadata:
        return {}
    stripped = {
        key: value
        for key, value in metadata.items()
        if str(key) not in RUNTIME_METADATA_KEYS
    }
    safe = make_json_safe_for_execution_log(stripped)
    return safe if isinstance(safe, dict) else {"value": safe}
