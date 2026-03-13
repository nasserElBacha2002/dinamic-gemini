"""
Inventory domain entity — v3.0 (Documento técnico §7.1).

Represents an inventory session. States: draft → processing → in_review | completed | failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class InventoryStatus(str, Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Inventory:
    id: str
    name: str
    status: InventoryStatus
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    def mark_processing(self, now: datetime) -> None:
        self.status = InventoryStatus.PROCESSING
        self.updated_at = now

    def mark_completed(self, now: datetime) -> None:
        self.status = InventoryStatus.COMPLETED
        self.completed_at = now
        self.updated_at = now

    def mark_failed(self, now: datetime) -> None:
        self.status = InventoryStatus.FAILED
        self.updated_at = now
