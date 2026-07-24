"""Execute / cancel server reprocess runs (Phase 7)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from src.application.ports.server_reprocess_repository import ServerReprocessRepository
from src.application.use_cases.aisles.build_server_reprocess_proposals import (
    BuildServerReprocessProposals,
    ServerReprocessInvalidStateError,
    ServerReprocessRunNotFoundError,
)
from src.domain.server_reprocess.entities import (
    RemoteProposalInput,
    ServerReprocessProposal,
    ServerReprocessRun,
    ServerReprocessRunStatus,
)

logger = logging.getLogger(__name__)

_CANCELABLE = frozenset(
    {
        ServerReprocessRunStatus.REQUESTED.value,
        ServerReprocessRunStatus.QUEUED.value,
        ServerReprocessRunStatus.RUNNING.value,
    }
)


class ExecuteServerReprocessRun:
    """
    Attach remote strategy outputs as proposals.

    Does not call ProcessingResultPersister / does not overwrite current authority.
    Production workers should feed RemoteProposalInput after running existing strategies.
    """

    def __init__(
        self,
        *,
        reprocess_repo: ServerReprocessRepository,
        builder: BuildServerReprocessProposals | None = None,
        clock: Any = None,
    ) -> None:
        self._repo = reprocess_repo
        self._builder = builder or BuildServerReprocessProposals(
            reprocess_repo=reprocess_repo, clock=clock
        )
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(timezone.utc)

    def mark_running(self, run_id: str, *, linked_job_id: str | None = None) -> ServerReprocessRun:
        run = self._repo.get_run(run_id)
        if run is None:
            raise ServerReprocessRunNotFoundError(run_id)
        if run.status == ServerReprocessRunStatus.CANCELED.value:
            raise ServerReprocessInvalidStateError("Run is canceled")
        now = self._now()
        updated = replace(
            run,
            status=ServerReprocessRunStatus.RUNNING.value,
            started_at=run.started_at or now,
            linked_job_id=linked_job_id or run.linked_job_id,
            updated_at=now,
            row_version=run.row_version + 1,
        )
        logger.info("server_reprocess_started run_id=%s", run_id)
        return self._repo.update_run(updated)

    def complete_with_remote_results(
        self,
        *,
        run_id: str,
        remote_results: Sequence[RemoteProposalInput],
    ) -> tuple[ServerReprocessRun, list[ServerReprocessProposal]]:
        run = self._repo.get_run(run_id)
        if run is None:
            raise ServerReprocessRunNotFoundError(run_id)
        if run.status == ServerReprocessRunStatus.REQUESTED.value:
            self.mark_running(run_id)
        return self._builder.execute(run_id=run_id, remote_results=remote_results)

    def fail(self, *, run_id: str, code: str, message: str) -> ServerReprocessRun:
        run = self._repo.get_run(run_id)
        if run is None:
            raise ServerReprocessRunNotFoundError(run_id)
        now = self._now()
        updated = replace(
            run,
            status=ServerReprocessRunStatus.FAILED.value,
            failed_at=now,
            completed_at=now,
            failure_code=code,
            failure_message=(message or "")[:500],
            updated_at=now,
            row_version=run.row_version + 1,
        )
        logger.info("server_reprocess_failed run_id=%s code=%s", run_id, code)
        return self._repo.update_run(updated)


class CancelServerReprocessRun:
    def __init__(
        self, *, reprocess_repo: ServerReprocessRepository, clock: Any = None
    ) -> None:
        self._repo = reprocess_repo
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(timezone.utc)

    def execute(self, *, run_id: str) -> ServerReprocessRun:
        run = self._repo.get_run(run_id)
        if run is None:
            raise ServerReprocessRunNotFoundError(run_id)
        if run.status not in _CANCELABLE:
            raise ServerReprocessInvalidStateError(
                f"Cannot cancel run in status {run.status}"
            )
        now = self._now()
        updated = replace(
            run,
            status=ServerReprocessRunStatus.CANCELED.value,
            canceled_at=now,
            updated_at=now,
            row_version=run.row_version + 1,
        )
        logger.info("server_reprocess_canceled run_id=%s", run_id)
        return self._repo.update_run(updated)
