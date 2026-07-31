"""Physical aisle location (shelf/rack/slot) — Phase 1 positioning foundation.

Distinct from CV ``Position`` (detected product/pallet review unit in ``domain.positions``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re


class AisleLocationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


def normalize_aisle_location_code(code: str) -> str:
    """Normalize location codes for uniqueness (trim + collapse internal whitespace + upper)."""
    collapsed = re.sub(r"\s+", " ", (code or "").strip())
    return collapsed.upper()


@dataclass
class AisleLocation:
    id: str
    client_id: str
    aisle_id: str
    code: str
    normalized_code: str
    status: AisleLocationStatus
    created_at: datetime
    updated_at: datetime
    display_name: str | None = None
    description: str | None = None
    created_by: str | None = None
