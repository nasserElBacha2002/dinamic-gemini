"""Build proposal rows from remote outputs against an immutable run snapshot."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from src.application.ports.server_reprocess_repository import ServerReprocessRepository
from src.application.services.server_reprocess_difference import (
    classify_server_reprocess_difference,
)
from src.domain.server_reprocess.entities import (
    RemoteProposalInput,
    ServerReprocessProposal,
    ServerReprocessProposalStatus,
    ServerReprocessReviewStatus,
    ServerReprocessRun,
    ServerReprocessRunStatus,
)

logger = logging.getLogger(__name__)

SERVER_REPROCESS_RUN_NOT_FOUND = "SERVER_REPROCESS_RUN_NOT_FOUND"
SERVER_REPROCESS_INVALID_STATE = "SERVER_REPROCESS_INVALID_STATE"
SERVER_REPROCESS_CANCELED = "SERVER_REPROCESS_CANCELED"


class ServerReprocessRunNotFoundError(Exception):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"Server reprocess run {run_id} not found")
        self.error_code = SERVER_REPROCESS_RUN_NOT_FOUND


class ServerReprocessInvalidStateError(Exception):
    def __init__(self, message: str, *, error_code: str = SERVER_REPROCESS_INVALID_STATE) -> None:
        super().__init__(message)
        self.error_code = error_code


class BuildServerReprocessProposals:
    """Persist remote results as proposals only — never writes positions/authority."""

    def __init__(self, *, reprocess_repo: ServerReprocessRepository, clock: Any = None) -> None:
        self._repo = reprocess_repo
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(timezone.utc)

    def execute(
        self,
        *,
        run_id: str,
        remote_results: Sequence[RemoteProposalInput],
        mark_completed: bool = True,
    ) -> tuple[ServerReprocessRun, list[ServerReprocessProposal]]:
        run = self._repo.get_run(run_id)
        if run is None:
            raise ServerReprocessRunNotFoundError(run_id)
        if run.status == ServerReprocessRunStatus.CANCELED.value:
            raise ServerReprocessInvalidStateError(
                "Run is canceled", error_code=SERVER_REPROCESS_CANCELED
            )
        if run.status in (
            ServerReprocessRunStatus.COMPLETED.value,
            ServerReprocessRunStatus.FAILED.value,
        ):
            # idempotent: return existing proposals
            return run, list(self._repo.list_proposals(run_id, limit=10_000))

        assets = {a.asset_id: a for a in self._repo.list_run_assets(run_id)}
        now = self._now()
        started = run.started_at or now
        proposals: list[ServerReprocessProposal] = []
        by_remote = {r.asset_id: r for r in remote_results}

        for asset_id, snap in assets.items():
            remote = by_remote.get(asset_id)
            if remote is None:
                remote = RemoteProposalInput(
                    asset_id=asset_id,
                    resolved=False,
                    comparable=True,
                )
            diff = classify_server_reprocess_difference(
                snapshot_asset=snap, remote=remote
            )
            status = (
                ServerReprocessProposalStatus.NOT_COMPARABLE.value
                if diff.value.startswith("NOT_COMPARABLE")
                else ServerReprocessProposalStatus.PROPOSED.value
            )
            proposals.append(
                ServerReprocessProposal(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    asset_id=asset_id,
                    remote_result_id=remote.remote_result_id,
                    previous_result_id=snap.previous_result_id,
                    previous_position_id=snap.previous_position_id,
                    status=status,
                    difference_type=diff.value,
                    internal_code=(remote.internal_code or None),
                    quantity=remote.quantity,
                    confidence=remote.confidence,
                    source=remote.source,
                    pipeline_version=remote.pipeline_version or run.pipeline_version,
                    remote_resolved=bool(remote.resolved),
                    review_status=ServerReprocessReviewStatus.NOT_REVIEWED.value,
                    created_at=now,
                    updated_at=now,
                )
            )

        saved_proposals = list(
            self._repo.replace_proposals(run_id=run_id, proposals=proposals)
        )
        updated = replace(
            run,
            status=(
                ServerReprocessRunStatus.COMPLETED.value
                if mark_completed
                else ServerReprocessRunStatus.RUNNING.value
            ),
            started_at=started,
            completed_at=now if mark_completed else None,
            updated_at=now,
            row_version=run.row_version + 1,
        )
        saved_run = self._repo.update_run(updated)
        logger.info(
            "server_reprocess_completed run_id=%s proposals=%s",
            run_id,
            len(saved_proposals),
        )
        return saved_run, saved_proposals
