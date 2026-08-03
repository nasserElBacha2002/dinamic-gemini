"""Deterministic in-memory manual position-override repository."""

from __future__ import annotations

from dataclasses import replace
from threading import RLock

from src.application.position_override_errors import (
    PositionOverrideConflictError,
    PositionOverrideIdempotencyConflictError,
)
from src.domain.position_overrides.entities import ManualProductPositionOverride


class MemoryManualPositionOverrideRepository:
    def __init__(self) -> None:
        self._rows: dict[str, ManualProductPositionOverride] = {}
        self._effective_versions: dict[tuple[str, str], int] = {}
        self._automatic_states: dict[
            tuple[str, str], tuple[str | None, str | None]
        ] = {}
        self._lock = RLock()

    def get_active(
        self, job_id: str, result_id: str
    ) -> ManualProductPositionOverride | None:
        return next(
            (
                row
                for row in self._rows.values()
                if row.job_id == job_id and row.result_id == result_id and row.is_active
            ),
            None,
        )

    def list_active_for_results(
        self, job_id: str, result_ids: list[str]
    ) -> dict[str, ManualProductPositionOverride]:
        wanted = set(result_ids)
        return {
            row.result_id: row
            for row in self._rows.values()
            if row.job_id == job_id and row.result_id in wanted and row.is_active
        }

    def get_effective_versions(
        self, job_id: str, result_ids: list[str]
    ) -> dict[str, int]:
        return {
            result_id: self._effective_versions.get((job_id, result_id), 0)
            for result_id in dict.fromkeys(result_ids)
        }

    def observe_automatic_state(
        self,
        job_id: str,
        result_id: str,
        reconciliation_id: str | None,
        assignment_id: str | None,
    ) -> None:
        """Record the latest automatic state seen by the in-memory read model."""
        with self._lock:
            self._automatic_states[(job_id, result_id)] = (
                reconciliation_id,
                assignment_id,
            )

    def list_history(
        self, job_id: str, result_id: str
    ) -> list[ManualProductPositionOverride]:
        rows = [
            row
            for row in self._rows.values()
            if row.job_id == job_id and row.result_id == result_id
        ]
        return sorted(rows, key=lambda row: (row.version, row.created_at), reverse=True)

    def get_by_idempotency_key(
        self, client_id: str, idempotency_key: str
    ) -> ManualProductPositionOverride | None:
        return next(
            (
                row
                for row in self._rows.values()
                if row.client_id == client_id and row.idempotency_key == idempotency_key
            ),
            None,
        )

    def insert_revision_atomically(
        self,
        revision: ManualProductPositionOverride,
        *,
        expected_effective_version: int,
        expected_automatic_reconciliation_id: str | None,
        expected_automatic_assignment_id: str | None,
        expected_active_override_id: str | None,
        expected_active_override_version: int | None,
    ) -> ManualProductPositionOverride:
        with self._lock:
            replay = self.get_by_idempotency_key(
                revision.client_id, revision.idempotency_key
            )
            if replay is not None:
                if (
                    replay.job_id == revision.job_id
                    and replay.result_id == revision.result_id
                    and replay.override_action is revision.override_action
                    and replay.new_position_label_id == revision.new_position_label_id
                    and replay.reason_code is revision.reason_code
                    and replay.reason_text == revision.reason_text
                ):
                    return replay
                raise PositionOverrideIdempotencyConflictError(
                    "Idempotency key was already used for another override request."
                )
            key = (revision.job_id, revision.result_id)
            current = self._effective_versions.get(key, 0)
            if current != expected_effective_version:
                raise PositionOverrideConflictError(
                    "The effective position changed.",
                    current_version=current,
                )
            automatic_state = self._automatic_states.get(
                key,
                (
                    revision.automatic_reconciliation_id,
                    revision.automatic_assignment_id,
                ),
            )
            if automatic_state != (
                expected_automatic_reconciliation_id,
                expected_automatic_assignment_id,
            ):
                raise PositionOverrideConflictError(
                    "The automatic position assignment changed.",
                    current_version=current,
                )
            active = self.get_active(revision.job_id, revision.result_id)
            current_active = (
                (active.id, active.version) if active is not None else (None, None)
            )
            if current_active != (
                expected_active_override_id,
                expected_active_override_version,
            ):
                raise PositionOverrideConflictError(
                    "The active manual override changed.",
                    current_version=current,
                )
            if active is not None:
                self._rows[active.id] = replace(
                    active,
                    is_active=False,
                    updated_at=revision.created_at,
                    deactivated_at=revision.created_at,
                )
            next_version = current + 1
            saved = replace(revision, version=next_version)
            self._rows[saved.id] = saved
            self._effective_versions[key] = next_version
            return saved
