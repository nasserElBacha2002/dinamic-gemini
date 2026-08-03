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
        expected_active_version: int,
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
            active = self.get_active(revision.job_id, revision.result_id)
            current = active.version if active else 0
            if current != expected_active_version:
                raise PositionOverrideConflictError(
                    "The effective position changed.",
                    current_version=current,
                )
            if active is not None:
                self._rows[active.id] = replace(
                    active,
                    is_active=False,
                    updated_at=revision.created_at,
                    deactivated_at=revision.created_at,
                )
            self._rows[revision.id] = revision
            return revision
