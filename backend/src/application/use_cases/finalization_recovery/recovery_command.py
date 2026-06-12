"""Shared recovery command — Phase 3.4."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryCommand:
    job_id: str
    dry_run: bool = False
    requested_by: str = "admin"
    source: str = "api"
    allow_canceled_terminalization: bool = False
    include_optional_artifacts: bool = False
