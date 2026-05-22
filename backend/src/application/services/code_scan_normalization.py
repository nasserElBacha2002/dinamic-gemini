"""Minimal code value normalization for aisle code scans."""

from __future__ import annotations


def normalize_code_value(raw: str) -> str:
    """Trim whitespace only; preserve original semantics (no GS1/fuzzy parsing)."""
    return (raw or "").strip()


def code_value_within_limit(value: str, max_length: int) -> bool:
    return len(value) <= max_length
