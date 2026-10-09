"""Shared doubles and harness for v3 job executor operational-safety tests."""

from tests.support.worker_executor_harness.doubles import (
    ArtifactUploadSpy,
    FailingArtifactStore,
    FailingRecomputeUseCase,
    FailOnNthSavePositionRepository,
    PartialFailingAisleRepository,
    PartialFailingJobRepository,
    RecordingPipelineRunner,
)
from tests.support.worker_executor_harness.executor_harness import (
    ExecutorHarness,
    build_recompute_use_case,
    make_two_entity_hybrid_report,
)

__all__ = [
    "ArtifactUploadSpy",
    "ExecutorHarness",
    "FailOnNthSavePositionRepository",
    "FailingArtifactStore",
    "FailingRecomputeUseCase",
    "PartialFailingAisleRepository",
    "PartialFailingJobRepository",
    "RecordingPipelineRunner",
    "build_recompute_use_case",
    "make_two_entity_hybrid_report",
]
