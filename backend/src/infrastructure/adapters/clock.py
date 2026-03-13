"""
Clock adapter — returns current UTC time.

Use this in production; use a fixed or mock clock in tests.
"""

from __future__ import annotations

from datetime import datetime, timezone


class UtcClock:
    """Clock implementation using datetime.now(timezone.utc)."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)
