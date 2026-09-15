"""Worker poll claim-cycle outcomes (embedded / dedicated worker).

Distinct from :mod:`src.domain.jobs.claim` (STARTING→RUNNING ownership CAS).
This module describes one **queue poll** against v3 ``inventory_jobs`` and the
optional legacy Stage-8 ``jobs`` bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.jobs.models import JobRecord


class WorkerClaimCycleStatus(str, Enum):
    """Explicit poll outcomes — never conflate empty queue with claim failure."""

    JOB_CLAIMED = "JOB_CLAIMED"
    IDLE_HEALTHY = "IDLE_HEALTHY"
    CLAIM_UNAVAILABLE = "CLAIM_UNAVAILABLE"


class LegacyBridgeMode(str, Enum):
    """How the Stage-8 ``jobs`` SQL bridge participates in a poll.

    Only two modes are supported. Absence of the ``jobs`` table is **not** a
    feature flag: under ``DRAIN_REQUIRED`` a missing/broken bridge is
    ``CLAIM_UNAVAILABLE``. Under ``DISABLED`` the bridge is never consulted.
    """

    DISABLED = "DISABLED"
    DRAIN_REQUIRED = "DRAIN_REQUIRED"


def resolve_legacy_bridge_mode(settings: object) -> LegacyBridgeMode:
    """Map settings to an explicit bridge mode (no ambiguous boolean alone)."""
    if bool(getattr(settings, "legacy_stage8_sql_bridge_disabled", False)):
        return LegacyBridgeMode.DISABLED
    return LegacyBridgeMode.DRAIN_REQUIRED


@dataclass(frozen=True)
class WorkerClaimCycleResult:
    status: WorkerClaimCycleStatus
    job: JobRecord | None = None
    detail: str | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        if self.status is WorkerClaimCycleStatus.JOB_CLAIMED and self.job is None:
            raise ValueError("JOB_CLAIMED requires a non-None job")
        if self.status is WorkerClaimCycleStatus.IDLE_HEALTHY and self.job is not None:
            raise ValueError("IDLE_HEALTHY requires job is None")
        if self.status is WorkerClaimCycleStatus.CLAIM_UNAVAILABLE and self.job is not None:
            raise ValueError("CLAIM_UNAVAILABLE requires job is None")

    @property
    def is_healthy(self) -> bool:
        return self.status in (
            WorkerClaimCycleStatus.JOB_CLAIMED,
            WorkerClaimCycleStatus.IDLE_HEALTHY,
        )
