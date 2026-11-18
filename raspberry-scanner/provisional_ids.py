"""Identifiers for entities created locally before backend reconciliation."""

from __future__ import annotations

# Mirrors backend src/domain/dinamic_scanner_txt/constants.py
PENDING_AISLE_ID = "00000000-0000-4000-8000-000000000001"


def is_pending_aisle_id(aisle_id: str | None) -> bool:
    return (aisle_id or "").strip() == PENDING_AISLE_ID