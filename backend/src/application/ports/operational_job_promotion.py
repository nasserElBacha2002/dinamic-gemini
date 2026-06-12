"""Operational job promotion port — Phase 2 Part 3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class PromotionOutcome(str, Enum):
    PROMOTED = "promoted"
    ALREADY_OPERATIONAL = "already_operational"
    REJECTED_STALE = "rejected_stale"
    REJECTED_INVALID_STATUS = "rejected_invalid_status"
    REJECTED_WRONG_AISLE = "rejected_wrong_aisle"
    REJECTED_INVALID_JOB_TYPE = "rejected_invalid_job_type"
    REJECTED_JOB_NOT_FOUND = "rejected_job_not_found"
    REJECTED_AISLE_NOT_FOUND = "rejected_aisle_not_found"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class PromotionResult:
    outcome: PromotionOutcome
    previous_job_id: str | None
    operational_job_id: str | None


class OperationalJobPromotionRepository(Protocol):
    """Atomic compare-and-set promotion for ``aisles.operational_job_id``."""

    def promote_if_eligible(
        self,
        *,
        aisle_id: str,
        candidate_job_id: str,
        candidate_created_at: object,
    ) -> PromotionResult:
        """Promote when candidate ordering is >= current operational job (by ``created_at``)."""
