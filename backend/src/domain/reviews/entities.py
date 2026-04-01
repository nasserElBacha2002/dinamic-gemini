"""
ReviewAction domain entity — v3.0 (Documento técnico §7.7).

Manual review action on a position: confirm, update_quantity, update_sku,
mark_unknown (operator-marked unknown), delete_position.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class ReviewActionType(str, Enum):
    CONFIRM = "confirm"
    UPDATE_QUANTITY = "update_quantity"
    UPDATE_SKU = "update_sku"
    MARK_UNKNOWN = "mark_unknown"
    DELETE_POSITION = "delete_position"


@dataclass
class ReviewAction:
    id: str
    position_id: str
    action_type: ReviewActionType
    before_json: Dict[str, Any]
    after_json: Dict[str, Any]
    created_at: datetime
    user_id: Optional[str] = None
    comment: Optional[str] = None
