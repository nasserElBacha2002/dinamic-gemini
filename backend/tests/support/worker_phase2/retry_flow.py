"""Production-level retry wiring for Phase 2 characterization tests."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.use_cases.aisles.retry_aisle_job import RetryAisleJobUseCase
from tests.support.worker_phase1.executor_harness import ExecutorHarness, FixedClock


@dataclass
class RetryFlowServices:
    retry_use_case: RetryAisleJobUseCase
    worker_launch: RecordingWorkerLaunchService


class RecordingWorkerLaunchService:
    """Records worker launch calls without spawning a real worker."""

    def __init__(self) -> None:
        self.launched: list[str] = []

    def launch(self, job_id: str) -> str:
        self.launched.append(job_id)
        return f"exec-{job_id}"


def build_retry_flow_services(harness: ExecutorHarness) -> RetryFlowServices:
    clock = FixedClock(harness.now)
    reconciler = InventoryStatusReconciler(
        harness.inventory_repo,
        harness.aisle_repo,
        clock,
    )
    launcher = RecordingWorkerLaunchService()
    launch_service = AisleJobLaunchService(
        aisle_repo=harness.aisle_repo,
        job_repo=harness.job_repo,
        worker_launch_service=launcher,
        clock=clock,
        status_reconciler=reconciler,
    )
    stale_reconciler = JobStaleReconciler(
        job_repo=harness.job_repo,
        clock=clock,
        stale_after_seconds=900,
    )
    return RetryFlowServices(
        retry_use_case=RetryAisleJobUseCase(
            aisle_repo=harness.aisle_repo,
            job_repo=harness.job_repo,
            launch_service=launch_service,
            stale_reconciler=stale_reconciler,
        ),
        worker_launch=launcher,
    )
