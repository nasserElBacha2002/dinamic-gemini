"""Persistence port for immutable manual position-override revisions."""

from __future__ import annotations

from typing import Protocol

from src.domain.position_overrides.entities import ManualProductPositionOverride


class ManualPositionOverrideRepository(Protocol):
    def get_active(
        self, job_id: str, result_id: str
    ) -> ManualProductPositionOverride | None: ...

    def list_active_for_results(
        self, job_id: str, result_ids: list[str]
    ) -> dict[str, ManualProductPositionOverride]: ...

    def get_effective_versions(
        self, job_id: str, result_ids: list[str]
    ) -> dict[str, int]: ...

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
        expected_effective_version: int,
        expected_automatic_reconciliation_id: str | None,
        expected_automatic_assignment_id: str | None,
        expected_active_override_id: str | None,
        expected_active_override_version: int | None,
    ) -> ManualProductPositionOverride: ...
