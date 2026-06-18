"""Deterministic canonical JSON helpers for traceability artifact hashing."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_json_bytes(obj: Any) -> bytes:
    return canonical_json_dumps(obj).encode("utf-8")


def sha256_canonical_json(obj: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()
