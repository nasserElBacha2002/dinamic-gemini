"""Normalize SQL driver cell values to str for safe stripping and enum parsing (B2.3)."""

from __future__ import annotations

def normalize_db_str(raw: object) -> str:
    """Strip whitespace from a DB cell; never assume the driver returns str."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    return str(raw).strip()


def optional_nonempty_db_str(raw: object) -> str | None:
    """Return stripped string or None if empty after normalization."""
    s = normalize_db_str(raw)
    return s or None
