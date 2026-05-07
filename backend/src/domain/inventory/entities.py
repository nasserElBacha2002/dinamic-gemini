"""
Inventory domain entity — v3.0 (Documento técnico §7.1).

Represents an inventory session.

Persisted states: draft → processing → in_review → completed | failed.
`draft`: no aisles. Once aisles exist, status is reconciled from aisle aggregates
(see `derive_inventory_status_from_aisles` + `InventoryStatusReconciler`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class InventoryStatus(str, Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    FAILED = "failed"


class InventoryProcessingMode(str, Enum):
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class Inventory:
    id: str
    name: str
    status: InventoryStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    processing_mode: InventoryProcessingMode = InventoryProcessingMode.PRODUCTION
    primary_provider_name: str | None = None
    primary_model_name: str | None = None
    primary_prompt_key: str | None = None
    primary_prompt_version: str | None = None
    client_id: str | None = None

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
