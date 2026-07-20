"""In-memory AssetProcessingCommandRepository."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime

from src.application.ports.asset_processing_command_repository import (
    AssetProcessingCommandRepository,
)
from src.domain.image_processing.asset_processing_command import (
    AssetProcessingCommand,
    AssetProcessingCommandStatus,
)


class MemoryAssetProcessingCommandRepository(AssetProcessingCommandRepository):
    def __init__(self) -> None:
        self._rows: dict[str, AssetProcessingCommand] = {}
        self._lock = threading.Lock()

    def save(self, command: AssetProcessingCommand) -> None:
        with self._lock:
            self._rows[command.id] = deepcopy(command)

    def get_by_id(self, command_id: str) -> AssetProcessingCommand | None:
        with self._lock:
            row = self._rows.get(command_id)
            return deepcopy(row) if row else None

    def list_by_job_asset(
        self, job_id: str, asset_id: str, *, limit: int = 50
    ) -> Sequence[AssetProcessingCommand]:
        with self._lock:
            matched = [
                deepcopy(c)
                for c in self._rows.values()
                if c.job_id == job_id and c.asset_id == asset_id
            ]
        matched.sort(key=lambda c: c.created_at, reverse=True)
        return matched[:limit]

    def try_claim(
        self,
        command_id: str,
        *,
        worker_token: str,
        now: datetime,
    ) -> AssetProcessingCommand | None:
        with self._lock:
            row = self._rows.get(command_id)
            if row is None or row.status is not AssetProcessingCommandStatus.QUEUED:
                return None
            row.status = AssetProcessingCommandStatus.CLAIMED
            row.worker_token = worker_token
            row.claimed_at = now
            self._rows[command_id] = row
            return deepcopy(row)

    def try_claim_next_queued(
        self,
        *,
        worker_token: str,
        now: datetime,
        job_id: str | None = None,
    ) -> AssetProcessingCommand | None:
        with self._lock:
            candidates = [
                c
                for c in self._rows.values()
                if c.status is AssetProcessingCommandStatus.QUEUED
                and (job_id is None or c.job_id == job_id)
            ]
            candidates.sort(key=lambda c: c.created_at)
            if not candidates:
                return None
            row = candidates[0]
            row.status = AssetProcessingCommandStatus.CLAIMED
            row.worker_token = worker_token
            row.claimed_at = now
            self._rows[row.id] = row
            return deepcopy(row)

    def mark_running(self, command: AssetProcessingCommand, *, now: datetime) -> None:
        with self._lock:
            row = self._rows.get(command.id)
            if row is None:
                return
            row.status = AssetProcessingCommandStatus.RUNNING
            self._rows[row.id] = row

    def mark_finished(self, command: AssetProcessingCommand, *, now: datetime) -> None:
        with self._lock:
            self._rows[command.id] = deepcopy(command)
            self._rows[command.id].completed_at = now


__all__ = ["MemoryAssetProcessingCommandRepository"]
