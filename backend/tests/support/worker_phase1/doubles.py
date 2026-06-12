"""Deterministic test doubles for worker Phase 1 operational safety characterization."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

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

    def __init__(self) -> None:
        self.execute_calls = 0

    def execute(
        self, command: RecomputeConsolidatedCountsCommand
    ) -> RecomputeConsolidatedCountsResult:
        self.execute_calls += 1
        raise RuntimeError("simulated recompute failure")


class FailingArtifactStore:
    """Artifact store double that fails ``put_object`` after optional successful uploads."""

    def __init__(self, *, fail_on_call: int = 1) -> None:
        self.put_object_calls = 0
        self._fail_on_call = fail_on_call
        self.uploaded_keys: list[str] = []

    def put_object(self, path: str, file_obj: Any, content_type: str) -> Any:
        self.put_object_calls += 1
        if self.put_object_calls >= self._fail_on_call:
            raise RuntimeError("simulated durable artifact upload failure")
        payload = file_obj.read()
        self.uploaded_keys.append(path)
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

    def delete_file(self, path: str) -> None:
        pass


class ArtifactUploadSpy(FailingArtifactStore):
    """Records successful uploads; never fails."""

    def __init__(self) -> None:
        super().__init__(fail_on_call=10_000)


class PartialFailingJobRepository(JobRepository):
    """Fails ``save`` when persisting a job transitioning to SUCCEEDED."""

    def __init__(self, inner: JobRepository) -> None:
        self._inner = inner
        self.save_calls = 0

    def save(self, job: Job) -> None:
        self.save_calls += 1
        if job.status == JobStatus.SUCCEEDED:
            raise RuntimeError("simulated job mark_success save failure")
        self._inner.save(job)

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


class PartialFailingAisleRepository(AisleRepository):
    """Fails ``save`` when aisle status is PROCESSED (mark_success terminal aisle write)."""

    def __init__(self, inner: AisleRepository) -> None:
        self._inner = inner
        self.save_calls = 0

    def save(self, aisle: Aisle) -> None:
        self.save_calls += 1
        from src.domain.aisle.entities import AisleStatus

        if aisle.status == AisleStatus.PROCESSED:
            raise RuntimeError("simulated aisle mark_processed save failure")
        self._inner.save(aisle)

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._inner.get_by_id(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return self._inner.list_by_inventory(inventory_id)

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        return self._inner.get_by_inventory_and_code(inventory_id, code)


class RecordingPipelineRunner:
    """Wraps pipeline runner methods to count invocations and inject cancellation."""

    def __init__(self, inner: V3ProcessAislePipelineRunner) -> None:
        self._inner = inner
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
        from datetime import datetime, timezone

        job.status = JobStatus.CANCEL_REQUESTED
        job.cancel_requested_at = datetime.now(timezone.utc)
        self._job_repo_for_cancel.save(job)
