"""Deterministic test doubles for worker Phase 1 operational safety characterization."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import (
    JOB_ID_FILTER_UNSET,
    AisleRepository,
    JobRepository,
    PositionRepository,
)
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsResult,
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position
from src.infrastructure.pipeline.v3_process_aisle_pipeline_runner import (
    V3ProcessAislePipelineRunner,
)
from src.pipeline.contracts.analysis_context import AnalysisContext
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult


class FailOnNthSavePositionRepository(PositionRepository):
    """Delegates to an inner repo but raises on the Nth ``save`` call (1-based)."""

    def __init__(self, inner: PositionRepository, *, fail_on_call: int) -> None:
        self._inner = inner
        self._fail_on_call = fail_on_call
        self.save_calls = 0

    def save(self, position: Position) -> None:
        self.save_calls += 1
        if self.save_calls == self._fail_on_call:
            raise RuntimeError(
                f"simulated position save failure on call {self.save_calls}"
            )
        self._inner.save(position)

    def get_by_id(self, position_id: str) -> Position | None:
        return self._inner.get_by_id(position_id)

    def list_by_aisle(
        self,
        aisle_id: str,
        status: str | None = None,
        needs_review: bool | None = None,
        min_confidence: float | None = None,
        sku_filter: str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
        job_id: str | None | object = JOB_ID_FILTER_UNSET,
    ) -> Sequence[Position]:
        return self._inner.list_by_aisle(
            aisle_id,
            status=status,
            needs_review=needs_review,
            min_confidence=min_confidence,
            sku_filter=sku_filter,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
            job_id=job_id,
        )

    def list_by_aisle_query(
        self, aisle_id: str, query: PositionListQuery | None = None
    ) -> Sequence[Position]:
        return self._inner.list_by_aisle_query(aisle_id, query)

    def list_by_aisles(
        self,
        aisle_ids: Sequence[str],
        status: str | None = None,
        needs_review: bool | None = None,
        min_confidence: float | None = None,
        sku_filter: str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
        job_id: str | None | object = JOB_ID_FILTER_UNSET,
    ) -> Sequence[Position]:
        return self._inner.list_by_aisles(
            aisle_ids,
            status=status,
            needs_review=needs_review,
            min_confidence=min_confidence,
            sku_filter=sku_filter,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
            job_id=job_id,
        )


class FailingRecomputeUseCase(RecomputeConsolidatedCountsUseCase):
    """Raises on execute after optionally recording invocation."""

    def __init__(self, delegate: RecomputeConsolidatedCountsUseCase | None = None) -> None:
        self.execute_calls = 0
        self._delegate = delegate
        if delegate is not None:
            self._normalized_repo = delegate._normalized_repo
            self._final_repo = delegate._final_repo
            self._normalization = delegate._normalization
            self._builder = delegate._builder

    def execute(
        self, command: RecomputeConsolidatedCountsCommand
    ) -> RecomputeConsolidatedCountsResult:
        self.execute_calls += 1
        raise RuntimeError("simulated recompute failure")

    def run_persist_recompute(
        self,
        recompute: RecomputeConsolidatedCountsUseCase,
        command: RecomputeConsolidatedCountsCommand,
    ) -> RecomputeConsolidatedCountsResult:
        """Invoked by PersistAisleResultUseCase so failures use transaction-bound repos."""
        self.execute_calls += 1
        raise RuntimeError("simulated recompute failure")


ArtifactFailMode = Literal["exact", "from_onward"]


class FailingArtifactStore:
    """Artifact store double that fails ``put_object`` on a configured call.

    ``fail_mode``:
    - ``exact``: fail only when ``put_object_calls == fail_on_call``
    - ``from_onward``: fail when ``put_object_calls >= fail_on_call`` (default)
    """

    def __init__(
        self,
        *,
        fail_on_call: int = 1,
        fail_mode: ArtifactFailMode = "from_onward",
    ) -> None:
        self.put_object_calls = 0
        self._fail_on_call = fail_on_call
        self._fail_mode = fail_mode
        self.uploaded_keys: list[str] = []
        self.uploaded_sizes: dict[str, int] = {}
        self.uploaded_sha256: dict[str, str] = {}

    def _should_fail(self) -> bool:
        if self._fail_mode == "exact":
            return self.put_object_calls == self._fail_on_call
        return self.put_object_calls >= self._fail_on_call

    def put_object(self, path: str, file_obj: Any, content_type: str) -> Any:
        self.put_object_calls += 1
        if self._should_fail():
            raise RuntimeError("simulated durable artifact upload failure")
        payload = file_obj.read()
        self.uploaded_keys.append(path)
        self.uploaded_sizes[path] = len(payload)
        self.uploaded_sha256[path] = hashlib.sha256(payload).hexdigest()
        return type(
            "StoredArtifactStub",
            (),
            {
                "storage_provider": "local",
                "storage_bucket": None,
                "storage_key": path,
                "content_type": content_type,
                "file_size_bytes": len(payload),
                "etag": "etag-test",
            },
        )()

    def save_file(self, path: str, file_obj: Any, content_type: str) -> str:
        return path

    def object_exists(self, key: str) -> bool:
        return key in self.uploaded_sizes

    def object_size_bytes(self, key: str, *, bucket: str | None = None) -> int:
        return self.uploaded_sizes.get(key, 10)

    def get_object_metadata(self, key: str, *, bucket: str | None = None):
        from src.infrastructure.storage.artifact_store import StoredObjectMetadata

        _ = bucket
        if key not in self.uploaded_sizes:
            raise FileNotFoundError(key)
        return StoredObjectMetadata(
            file_size_bytes=self.uploaded_sizes[key],
            etag="etag-test",
            sha256=self.uploaded_sha256.get(key),
        )

    def delete_file(self, path: str) -> None:
        pass


class ArtifactUploadSpy(FailingArtifactStore):
    """Records successful uploads; never fails."""

    def __init__(self) -> None:
        super().__init__(fail_on_call=10_000)

    def object_exists(self, key: str) -> bool:
        return key in self.uploaded_sizes


@dataclass(frozen=True)
class SaveAttemptSnapshot:
    committed: bool
    status: str
    error_message: str | None
    failure_code: str | None


def _job_snapshot(job: Job) -> SaveAttemptSnapshot:
    return SaveAttemptSnapshot(
        committed=False,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        error_message=job.error_message,
        failure_code=job.failure_code,
    )


class PartialFailingJobRepository(JobRepository):
    """Fails ``save`` when persisting a job transitioning to SUCCEEDED; records attempts."""

    def __init__(self, inner: JobRepository) -> None:
        self._inner = inner
        self.save_calls = 0
        self.save_attempts: list[SaveAttemptSnapshot] = []

    def save(self, job: Job) -> None:
        self.save_calls += 1
        snap = _job_snapshot(job)
        if job.status == JobStatus.SUCCEEDED:
            self.save_attempts.append(
                SaveAttemptSnapshot(
                    committed=False,
                    status=snap.status,
                    error_message=snap.error_message,
                    failure_code=snap.failure_code,
                )
            )
            raise RuntimeError("simulated job mark_success save failure")
        self._inner.save(copy.deepcopy(job))
        committed = self._inner.get_by_id(job.id)
        assert committed is not None
        self.save_attempts.append(
            SaveAttemptSnapshot(
                committed=True,
                status=committed.status.value,
                error_message=committed.error_message,
                failure_code=committed.failure_code,
            )
        )

    def get_by_id(self, job_id: str) -> Job | None:
        return self._inner.get_by_id(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        return self._inner.get_latest_by_target(target_type, target_id)

    def get_latest_by_targets(
        self, target_type: str, target_ids: Sequence[str]
    ) -> dict[str, Job]:
        return self._inner.get_latest_by_targets(target_type, target_ids)

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        return self._inner.list_jobs_for_target(target_type, target_id, limit=limit)


@dataclass(frozen=True)
class AisleSaveAttemptSnapshot:
    committed: bool
    status: str
    operational_job_id: str | None
    error_code: str | None


def _aisle_snapshot(aisle: Aisle) -> AisleSaveAttemptSnapshot:
    return AisleSaveAttemptSnapshot(
        committed=False,
        status=aisle.status.value if hasattr(aisle.status, "value") else str(aisle.status),
        operational_job_id=aisle.operational_job_id,
        error_code=aisle.error_code,
    )


class PartialFailingAisleRepository(AisleRepository):
    """Fails ``save`` when aisle status is PROCESSED (mark_success terminal aisle write)."""

    def __init__(self, inner: AisleRepository) -> None:
        self._inner = inner
        self.save_calls = 0
        self.save_attempts: list[AisleSaveAttemptSnapshot] = []

    def save(self, aisle: Aisle) -> None:
        self.save_calls += 1
        from src.domain.aisle.entities import AisleStatus

        snap = _aisle_snapshot(aisle)
        if aisle.status == AisleStatus.PROCESSED:
            self.save_attempts.append(
                AisleSaveAttemptSnapshot(
                    committed=False,
                    status=snap.status,
                    operational_job_id=snap.operational_job_id,
                    error_code=snap.error_code,
                )
            )
            raise RuntimeError("simulated aisle mark_processed save failure")
        self._inner.save(copy.deepcopy(aisle))
        committed = self._inner.get_by_id(aisle.id)
        assert committed is not None
        self.save_attempts.append(
            AisleSaveAttemptSnapshot(
                committed=True,
                status=committed.status.value,
                operational_job_id=committed.operational_job_id,
                error_code=committed.error_code,
            )
        )

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._inner.get_by_id(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return self._inner.list_by_inventory(inventory_id)

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        return self._inner.get_by_inventory_and_code(inventory_id, code)


class RecordingPipelineRunner:
    """Wraps pipeline runner methods to count invocations and inject cancellation."""

    def __init__(
        self,
        inner: V3ProcessAislePipelineRunner,
        *,
        clock: Any | None = None,
    ) -> None:
        self._inner = inner
        self._clock = clock
        self.run_hybrid_pipeline_calls = 0
        self.build_analysis_context_calls = 0
        self.build_pipeline_input_calls = 0
        self._run_side_effect: Any = None
        self._cancel_at: str | None = None
        self._job_repo_for_cancel: JobRepository | None = None
        self._job_id_for_cancel: str | None = None

    def arm_cancel_before_hybrid_run(
        self, *, job_repo: JobRepository, job_id: str
    ) -> None:
        self._cancel_at = "pre_pipeline"
        self._job_repo_for_cancel = job_repo
        self._job_id_for_cancel = job_id

    def arm_cancel_after_provider(
        self, *, job_repo: JobRepository, job_id: str
    ) -> None:
        self._cancel_at = "post_pipeline"
        self._job_repo_for_cancel = job_repo
        self._job_id_for_cancel = job_id

    def set_run_side_effect(self, side_effect: Any) -> None:
        self._run_side_effect = side_effect

    def build_analysis_context(
        self, aisle: Any, *, inventory_client_id: str | None = None
    ) -> AnalysisContext:
        self.build_analysis_context_calls += 1
        return self._inner.build_analysis_context(
            aisle, inventory_client_id=inventory_client_id
        )

    def build_pipeline_input(self, *args: Any, **kwargs: Any) -> Any:
        self.build_pipeline_input_calls += 1
        return self._inner.build_pipeline_input(*args, **kwargs)

    def run_hybrid_pipeline(self, **kwargs: Any) -> PipelineRunResult:
        self.run_hybrid_pipeline_calls += 1
        if self._cancel_at == "pre_pipeline":
            self._set_cancel_requested()
            kwargs["cancellation_checkpoint"](
                "Pipeline", "pre_pipeline", "cancel before provider"
            )
        if self._run_side_effect is not None:
            result = self._run_side_effect(**kwargs)
        else:
            result = self._inner.run_hybrid_pipeline(**kwargs)
        if self._cancel_at == "post_pipeline":
            self._set_cancel_requested()
            kwargs["cancellation_checkpoint"](
                "Pipeline", "post_pipeline", "cancel after provider"
            )
        return result

    def _set_cancel_requested(self) -> None:
        if self._job_repo_for_cancel is None or self._job_id_for_cancel is None:
            return
        job = self._job_repo_for_cancel.get_by_id(self._job_id_for_cancel)
        if job is None:
            return
        if self._clock is not None:
            now = self._clock.now()
        else:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
        job.status = JobStatus.CANCEL_REQUESTED
        job.cancel_requested_at = now
        self._job_repo_for_cancel.save(job)
