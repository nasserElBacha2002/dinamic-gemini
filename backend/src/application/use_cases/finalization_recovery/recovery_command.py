"""Shared recovery command — Phase 3.4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.jobs.finalization_recovery import RecoveryResult


@dataclass(frozen=True)
class RecoveryExecutionContext:
    """Parent lease context for coordinated resume — children must not acquire their own lease."""

    recovery_id: str
    attempt_id: str
    requested_by: str
    source: str


@dataclass(frozen=True)
class RecoveryCommand:
    job_id: str
    dry_run: bool = False
    requested_by: str = "admin"
    source: str = "api"
    allow_canceled_terminalization: bool = False
    include_optional_artifacts: bool = False
    execution_context: RecoveryExecutionContext | None = None

    @property
    def lease_exempt(self) -> bool:
        return self.execution_context is not None


class RecoveryStepUseCase(Protocol):
    def execute(self, command: RecoveryCommand) -> RecoveryResult: ...
