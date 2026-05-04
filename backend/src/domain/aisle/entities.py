"""
Aisle domain entity — v3.0 (Documento técnico §7.2, §9.5).

Represents an aisle within an inventory. State machine: created → assets_uploaded → queued
→ processing → processed → in_review → completed; any operational state → failed.
Error fields (error_code, error_message, retryable) reflect operational failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AisleStatus(str, Enum):
    CREATED = "created"
    ASSETS_UPLOADED = "assets_uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Aisle:
    id: str
    inventory_id: str
    code: str
    status: AisleStatus
    created_at: datetime
    updated_at: datetime
    #: Canonical inventory_jobs row for default result reads (Phase 2); NULL = legacy aisle (null job_id rows).
    operational_job_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool | None = None

    def mark_assets_uploaded(self, now: datetime) -> None:
        self.status = AisleStatus.ASSETS_UPLOADED
        self.updated_at = now

    def revert_to_created_when_no_source_assets_remain(self, now: datetime) -> bool:
        """If the aisle was only marked as having uploads, revert to ``created`` when the last asset is removed.

        Returns True when ``status`` and ``updated_at`` were changed and the row should be persisted.
        """
        if self.status != AisleStatus.ASSETS_UPLOADED:
            return False
        self.status = AisleStatus.CREATED
        self.updated_at = now
        return True

    def mark_queued(self, now: datetime) -> None:
        self.status = AisleStatus.QUEUED
        self.updated_at = now

    def mark_processing(self, now: datetime) -> None:
        self.status = AisleStatus.PROCESSING
        self.updated_at = now

    def mark_processed(self, now: datetime) -> None:
        self.status = AisleStatus.PROCESSED
        self.updated_at = now
        # Successful pipeline completion clears any stale failure markers from a prior run.
        self.error_code = None
        self.error_message = None
        self.retryable = None

    def mark_in_review(self, now: datetime) -> None:
        self.status = AisleStatus.IN_REVIEW
        self.updated_at = now

    def mark_completed(self, now: datetime) -> None:
        self.status = AisleStatus.COMPLETED
        self.updated_at = now

    def mark_failed(
        self,
        now: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.status = AisleStatus.FAILED
        self.updated_at = now
        self.error_code = error_code
        self.error_message = error_message
        self.retryable = retryable
