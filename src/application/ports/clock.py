"""
Clock port — v3.0.

Provides current time to use cases so they remain testable and time-zone aware.
Implementations can use datetime.now(timezone.utc) or a fixed time in tests.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Port for obtaining current time. Use cases depend on this instead of calling datetime directly."""

    def now(self) -> datetime:
        """Return current time (prefer timezone-aware UTC)."""
        ...
