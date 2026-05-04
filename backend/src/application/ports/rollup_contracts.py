"""
Lightweight rollup DTOs for repository ports — no domain or heavy contracts imports.

Kept separate from ``contracts.py`` so infrastructure repos (e.g. SQL source_asset) can import
``AisleAssetRollup`` without pulling the full contracts module graph (avoids fragile import cycles
and "cannot import name" errors during partial initialization).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AisleAssetRollup:
    """Per-aisle upload summary for GET /inventories/{id}/aisles (batch, no N+1)."""

    count: int
    last_uploaded_at: datetime | None
