"""Persistence port for immutable manual position-override revisions."""

from __future__ import annotations

from typing import Protocol

from src.domain.position_overrides.entities import ManualProductPositionOverride


class ManualPositionOverrideRepository(Protocol):
    def get_active(
        self, job_id: str, result_id: str
    ) -> ManualProductPositionOverride | None: ...

    def list_history(
        self, job_id: str, result_id: str
    ) -> list[ManualProductPositionOverride]: ...

    def get_by_idempotency_key(
        self, client_id: str, idempotency_key: str
    ) -> ManualProductPositionOverride | None: ...

    def insert_revision_atomically(
        self,
        revision: ManualProductPositionOverride,
        *,
        expected_active_version: int,
    ) -> ManualProductPositionOverride: ...
