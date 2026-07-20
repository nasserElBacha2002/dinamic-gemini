"""Port — durable asset processing commands."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.image_processing.asset_processing_command import AssetProcessingCommand


class AssetProcessingCommandRepository(Protocol):
    def save(self, command: AssetProcessingCommand) -> None: ...

    def get_by_id(self, command_id: str) -> AssetProcessingCommand | None: ...

    def list_by_job_asset(
        self, job_id: str, asset_id: str, *, limit: int = 50
    ) -> Sequence[AssetProcessingCommand]: ...

    def try_claim(
        self,
        command_id: str,
        *,
        worker_token: str,
        now: datetime,
    ) -> AssetProcessingCommand | None:
        """Atomic QUEUED → CLAIMED. Returns None if already claimed/missing."""
        ...

    def try_claim_next_queued(
        self,
        *,
        worker_token: str,
        now: datetime,
        job_id: str | None = None,
    ) -> AssetProcessingCommand | None: ...

    def mark_running(self, command: AssetProcessingCommand, *, now: datetime) -> None: ...

    def mark_finished(self, command: AssetProcessingCommand, *, now: datetime) -> None: ...
