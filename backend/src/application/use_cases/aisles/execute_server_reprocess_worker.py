"""Execute a SERVER_REPROCESS run via existing strategies without position persistence."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from src.application.ports.server_reprocess_repository import ServerReprocessRepository
from src.application.services.server_reprocess_proposal_sink import (
    ServerReprocessProposalResultSink,
)
from src.application.use_cases.aisles.build_server_reprocess_proposals import (
    BuildServerReprocessProposals,
    ServerReprocessInvalidStateError,
    ServerReprocessRunNotFoundError,
)
from src.domain.assets.entities import SourceAsset
from src.domain.image_processing.contracts import ImageProcessingResult
from src.domain.server_reprocess.entities import (
    ServerReprocessProposal,
    ServerReprocessRun,
    ServerReprocessRunStatus,
)

logger = logging.getLogger(__name__)

SERVER_REPROCESS_WORKER_FAILED = "SERVER_REPROCESS_WORKER_FAILED"
SERVER_REPROCESS_MODE_UNAVAILABLE = "SERVER_REPROCESS_MODE_UNAVAILABLE"


class ServerReprocessWorkerFailedError(Exception):
    def __init__(self, message: str, *, error_code: str = SERVER_REPROCESS_WORKER_FAILED) -> None:
        super().__init__(message)
        self.error_code = error_code


class _AssetRepo(Protocol):
    def get_by_id(self, asset_id: str) -> SourceAsset | None: ...


class _Strategy(Protocol):
    def process_asset(self, asset: SourceAsset) -> ImageProcessingResult: ...


AssetStrategyFactory = Callable[[str], _Strategy | None]


class ExecuteServerReprocessWorker:
    """
    Worker path for SERVER_REPROCESS:
    claim run → process snapshot assets with strategy → sink proposals → COMPLETED.
    Never calls ProcessingResultPersister.
    """

    def __init__(
        self,
        *,
        reprocess_repo: ServerReprocessRepository,
        asset_repo: _AssetRepo,
        strategy_factory: AssetStrategyFactory,
        builder: BuildServerReprocessProposals | None = None,
        clock: Any = None,
    ) -> None:
        self._repo = reprocess_repo
        self._asset_repo = asset_repo
        self._strategy_factory = strategy_factory
        self._builder = builder or BuildServerReprocessProposals(
            reprocess_repo=reprocess_repo, clock=clock
        )
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(timezone.utc)

    def execute(self, *, run_id: str) -> tuple[ServerReprocessRun, list[ServerReprocessProposal]]:
        run = self._repo.get_run(run_id)
        if run is None:
            raise ServerReprocessRunNotFoundError(run_id)
        if run.status == ServerReprocessRunStatus.CANCELED.value:
            raise ServerReprocessInvalidStateError("Run is canceled")
        if run.status == ServerReprocessRunStatus.COMPLETED.value:
            return run, list(self._repo.list_proposals(run_id, limit=10_000))

        now = self._now()
        running = replace(
            run,
            status=ServerReprocessRunStatus.RUNNING.value,
            started_at=run.started_at or now,
            updated_at=now,
            row_version=run.row_version + 1,
        )
        self._repo.update_run(running)
        logger.info("server_reprocess_started run_id=%s mode=%s", run_id, run.processing_mode)

        strategy = self._strategy_factory(run.processing_mode)
        if strategy is None:
            failed = replace(
                running,
                status=ServerReprocessRunStatus.FAILED.value,
                failed_at=now,
                completed_at=now,
                failure_code=SERVER_REPROCESS_MODE_UNAVAILABLE,
                failure_message=f"Mode unavailable: {run.processing_mode}",
                updated_at=now,
                row_version=running.row_version + 1,
            )
            self._repo.update_run(failed)
            raise ServerReprocessWorkerFailedError(
                f"Mode unavailable: {run.processing_mode}",
                error_code=SERVER_REPROCESS_MODE_UNAVAILABLE,
            )

        sink = ServerReprocessProposalResultSink()
        assets = list(self._repo.list_run_assets(run_id))
        try:
            for snap in assets:
                # Re-check cancel between assets
                latest = self._repo.get_run(run_id)
                if latest is not None and latest.status == ServerReprocessRunStatus.CANCELED.value:
                    raise ServerReprocessInvalidStateError("Run canceled during execution")
                asset = self._asset_repo.get_by_id(snap.asset_id)
                if asset is None:
                    continue
                result = strategy.process_asset(asset)
                sink.accept(result)
        except ServerReprocessInvalidStateError:
            raise
        except Exception as exc:
            failed = replace(
                running,
                status=ServerReprocessRunStatus.FAILED.value,
                failed_at=self._now(),
                completed_at=self._now(),
                failure_code=SERVER_REPROCESS_WORKER_FAILED,
                failure_message=str(exc)[:500],
                updated_at=self._now(),
                row_version=running.row_version + 1,
            )
            self._repo.update_run(failed)
            logger.exception("server_reprocess_failed run_id=%s", run_id)
            raise ServerReprocessWorkerFailedError(str(exc)) from exc

        return self._builder.execute(
            run_id=run_id, remote_results=sink.as_remote_inputs(), mark_completed=True
        )
