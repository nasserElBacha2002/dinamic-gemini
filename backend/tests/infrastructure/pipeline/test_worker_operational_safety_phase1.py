"""WKR Phase 1 — worker operational safety characterization tests (Blocks 1–3 + partial finalization)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.aisle.entities import AisleStatus
from src.domain.inventory.entities import InventoryStatus
from src.domain.jobs.entities import JobStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.llm.deepseek_sdk_adapter import DeepSeekSdkAdapter
from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest
from tests.support.worker_phase1.doubles import (
    ArtifactUploadSpy,
    FailingArtifactStore,
    FailingRecomputeUseCase,
    FailOnNthSavePositionRepository,
    PartialFailingAisleRepository,
    PartialFailingJobRepository,
    RecordingPipelineRunner,
)
from tests.support.worker_phase1.executor_harness import (
    ExecutorHarness,
    FixedClock,
    make_two_entity_hybrid_report,
)
from tests.support.worker_phase1.spies import ExecutionSpy

# --- Block 1: WKR-P1-T001 -----------------------------------------------------


def test_wkr_p1_t001_persist_fails_on_second_position_leaves_first_entity_committed(
    tmp_path,
) -> None:
    """WKR-P1-T001: mid-persist failure leaves earlier domain rows committed (non-atomic)."""
    inner_pos = MemoryPositionRepository()
    failing_pos = FailOnNthSavePositionRepository(inner_pos, fail_on_call=2)
    harness = ExecutorHarness.build(tmp_path, position_repo=failing_pos)
    executor = harness.make_executor()
    report = make_two_entity_hybrid_report()

    handled = harness.run_with_mock_pipeline(executor, report=report)

    assert handled is True
    assert failing_pos.save_calls == 2
    assert harness.pipeline_invocations == 1

    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.error_message is not None
    assert job.error_message.startswith("Persist:")
    assert job.failure_code == "PROCESSING_FAILED"

    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.FAILED

    inv = harness.inventory_repo.get_by_id(harness.inventory_id)
    assert inv is not None
    assert inv.status == InventoryStatus.FAILED

    committed = harness.positions_for_job(harness.job_id)
    assert len(committed) == 1
    assert committed[0].job_id == harness.job_id

    assert len(list(harness.product_repo.list_by_position(committed[0].id))) == 1
    assert harness.execution_log_text()
    assert "Persist" in harness.execution_log_text() or "Persist failed" in (
        job.error_message or ""
    )

    harness2 = ExecutorHarness.build(
        tmp_path / "retry",
        job_id="job-retry",
        position_repo=failing_pos._inner,
        artifact_store=ArtifactUploadSpy(),
    )
    harness2.run_with_mock_pipeline(harness2.make_executor())
    assert len(harness2.positions_for_job("job-retry")) == 2


# --- Block 1: WKR-P1-T007 -----------------------------------------------------


def test_wkr_p1_t007_recompute_failure_after_entity_persist_marks_job_failed(
    tmp_path,
) -> None:
    """WKR-P1-T007: entity rows persist; recompute failure fails job; aggregates may be empty."""
    failing_recompute = FailingRecomputeUseCase()
    harness = ExecutorHarness.build(tmp_path, recompute_uc=failing_recompute)
    executor = harness.make_executor()

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert failing_recompute.execute_calls == 1
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert "Persist:" in (job.error_message or "")

    positions = harness.positions_for_job()
    assert len(positions) == 2
    # Recompute failed before normalized/final layers were written for this scope.
    assert (
        len(
            list(
                harness.norm_repo.list_for_scope(
                    harness.inventory_id, harness.aisle_id, job_id=harness.job_id
                )
            )
        )
        == 0
    )


# --- Block 1: WKR-P1-T012 -----------------------------------------------------


def test_wkr_p1_t012_retry_isolates_job_scoped_results_safe_with_conditions(
    tmp_path,
) -> None:
    """WKR-P1-T012: partial fail job-1 rows remain; job-2 operational slice is isolated."""
    inner_pos = MemoryPositionRepository()
    failing_pos = FailOnNthSavePositionRepository(inner_pos, fail_on_call=2)

    harness1 = ExecutorHarness.build(
        tmp_path,
        job_id="job-fail-partial",
        position_repo=failing_pos,
    )
    executor1 = harness1.make_executor()
    harness1.run_with_mock_pipeline(executor1)

    partial_rows = harness1.positions_for_job("job-fail-partial")
    assert len(partial_rows) == 1

    aisle = harness1.aisle_repo.get_by_id(harness1.aisle_id)
    assert aisle is not None
    aisle.status = AisleStatus.QUEUED
    aisle.operational_job_id = None
    aisle.error_code = None
    aisle.error_message = None
    harness1.aisle_repo.save(aisle)

    harness2 = ExecutorHarness.build(
        tmp_path,
        job_id="job-success",
        job_status=JobStatus.STARTING,
        aisle_status=AisleStatus.QUEUED,
        job_repo=harness1.job_repo,
        aisle_repo=harness1.aisle_repo,
        inventory_repo=harness1.inventory_repo,
        position_repo=inner_pos,
        product_repo=harness1.product_repo,
        evidence_repo=harness1.evidence_repo,
        raw_repo=harness1.raw_repo,
        norm_repo=harness1.norm_repo,
        final_repo=harness1.final_repo,
    )

    executor2 = harness2.make_executor(artifact_store=ArtifactUploadSpy())
    harness2.run_with_mock_pipeline(executor2)

    success_job = harness2.job_repo.get_by_id("job-success")
    assert success_job is not None
    assert success_job.status == JobStatus.SUCCEEDED

    aisle_after = harness2.aisle_repo.get_by_id(harness2.aisle_id)
    assert aisle_after is not None
    assert aisle_after.status == AisleStatus.PROCESSED
    assert aisle_after.operational_job_id == "job-success"

    assert len(harness2.positions_for_job("job-fail-partial")) == 1
    assert len(harness2.positions_for_job("job-success")) == 2

    fail_products = [
        p
        for pos in harness2.positions_for_job("job-fail-partial")
        for p in harness2.product_repo.list_by_position(pos.id)
    ]
    success_products = [
        p
        for pos in harness2.positions_for_job("job-success")
        for p in harness2.product_repo.list_by_position(pos.id)
    ]
    assert len(fail_products) == 1
    assert len(success_products) == 2

    fail_evidence = [
        e
        for pos in harness2.positions_for_job("job-fail-partial")
        for e in harness2.evidence_repo.list_by_entity("position", pos.id)
    ]
    success_evidence = [
        e
        for pos in harness2.positions_for_job("job-success")
        for e in harness2.evidence_repo.list_by_entity("position", pos.id)
    ]
    assert len(fail_evidence) >= 1
    assert len(success_evidence) >= 2

    fail_raw = list(
        harness2.raw_repo.list_for_scope(
            harness2.inventory_id, harness2.aisle_id, job_id="job-fail-partial"
        )
    )
    success_raw = list(
        harness2.raw_repo.list_for_scope(
            harness2.inventory_id, harness2.aisle_id, job_id="job-success"
        )
    )
    assert len(fail_raw) == 0
    assert len(success_raw) >= 1

    list_uc = ListAislePositionsUseCase(
        harness2.inventory_repo,
        harness2.aisle_repo,
        harness2.position_repo,
        ResultContextResolver(harness2.job_repo, harness2.position_repo),
        harness2.product_repo,
        positions_aisle_raw_cap=500,
    )
    result = list_uc.execute(
        ListAislePositionsCommand(
            inventory_id=harness2.inventory_id,
            aisle_id=harness2.aisle_id,
            page=1,
            page_size=50,
        )
    )
    assert result.resolved_job_id == "job-success"
    assert {p.id for p in result.positions} == {p.id for p in harness2.positions_for_job("job-success")}
    assert not {p.id for p in result.positions} & {p.id for p in harness2.positions_for_job("job-fail-partial")}


# --- Block 2: WKR-P1-T002 -----------------------------------------------------


def test_wkr_p1_t002_artifact_failure_after_persist_leaves_domain_rows_failed_job(
    tmp_path,
) -> None:
    """WKR-P1-T002: job FAILED, results persisted=yes, artifacts published=no."""
    artifact_store = FailingArtifactStore(fail_on_call=1)
    harness = ExecutorHarness.build(tmp_path, artifact_store=artifact_store)
    executor = harness.make_executor()

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert artifact_store.put_object_calls >= 1
    assert artifact_store.uploaded_keys == []

    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert "Durable artifact upload failed" in (job.error_message or "")
    assert job.result_json is None or "durable_artifacts" not in (job.result_json or {})

    assert len(harness.positions_for_job()) == 2
    assert len(
        list(
            harness.raw_repo.list_for_scope(
                harness.inventory_id, harness.aisle_id, job_id=harness.job_id
            )
        )
    ) >= 1

    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.FAILED
    assert harness.pipeline_invocations == 1


# --- Block 2: WKR-P1-T003 -----------------------------------------------------


def test_wkr_p1_t003_case_a_mark_success_job_save_fails_after_artifacts(
    tmp_path,
) -> None:
    """WKR-P1-T003 Case A: artifacts uploaded; job SUCCEEDED save fails; outer handler marks FAILED."""
    artifact_store = ArtifactUploadSpy()
    inner_job = MemoryJobRepository()
    failing_job = PartialFailingJobRepository(inner_job)
    harness = ExecutorHarness.build(tmp_path, job_repo=failing_job, artifact_store=artifact_store)
    executor = harness.make_executor()
    spy = ExecutionSpy()
    spy.attach(executor, artifact_store=artifact_store)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert len(artifact_store.uploaded_keys) >= 2
    assert harness.pipeline_invocations == 1
    assert spy.persist_calls == 1
    assert spy.recompute_calls == 1
    assert spy.artifact_put_calls >= 2
    assert spy.mark_success_calls >= 1
    assert spy.fail_job_and_aisle_calls >= 1

    succeeded_attempts = [
        a for a in failing_job.save_attempts if a.status == JobStatus.SUCCEEDED.value
    ]
    assert succeeded_attempts
    assert all(not a.committed for a in succeeded_attempts)

    job = inner_job.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.FAILED
    assert len(harness.positions_for_job()) == 2


def test_wkr_p1_t003_case_b_aisle_save_fails_after_job_would_succeed(tmp_path) -> None:
    """WKR-P1-T003 Case B: aisle PROCESSED save fails after job SUCCEEDED committed (component)."""
    artifact_store = ArtifactUploadSpy()
    inner_aisle = MemoryAisleRepository()
    failing_aisle = PartialFailingAisleRepository(inner_aisle)
    harness = ExecutorHarness.build(tmp_path, aisle_repo=failing_aisle, artifact_store=artifact_store)
    executor = harness.make_executor()
    spy = ExecutionSpy()
    spy.attach(executor, artifact_store=artifact_store)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert len(artifact_store.uploaded_keys) >= 2
    assert spy.mark_success_calls >= 1
    assert spy.fail_job_and_aisle_calls >= 1

    processed_attempts = [
        a for a in failing_aisle.save_attempts if a.status == AisleStatus.PROCESSED.value
    ]
    assert processed_attempts
    assert all(not a.committed for a in processed_attempts)

    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    aisle = inner_aisle.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status != AisleStatus.PROCESSED
    assert aisle.status == AisleStatus.FAILED


def test_wkr_p1_t003_case_c_inventory_reconcile_fails_after_terminal_writes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WKR-P1-T003 Case C: reconcile failure surfaces as FAILED job after artifacts."""
    artifact_store = ArtifactUploadSpy()
    harness = ExecutorHarness.build(tmp_path, artifact_store=artifact_store)
    executor = harness.make_executor()
    spy = ExecutionSpy()
    spy.attach(executor, artifact_store=artifact_store)
    reconcile_calls: list[str] = []
    original_reconcile = executor._state._inventory_status_reconciler.reconcile

    def _fail_on_second_reconcile(inv_id: str) -> bool:
        reconcile_calls.append(inv_id)
        if len(reconcile_calls) == 2:
            raise RuntimeError("simulated inventory reconcile failure")
        return original_reconcile(inv_id)

    monkeypatch.setattr(
        executor._state._inventory_status_reconciler,
        "reconcile",
        _fail_on_second_reconcile,
    )

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert len(reconcile_calls) >= 2
    assert spy.persist_calls == 1
    assert spy.mark_success_calls >= 1
    assert spy.artifact_put_calls >= 2
    assert spy.fail_job_and_aisle_calls >= 1
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.FAILED
    assert len(artifact_store.uploaded_keys) >= 2


# --- Block 3: WKR-P1-T004 -----------------------------------------------------


def test_wkr_p1_t004_cancel_requested_before_executor_skips_pipeline_and_aisle_stays_queued(
    tmp_path,
) -> None:
    """WKR-P1-T004: documents job=CANCELED, aisle=queued characterization (audit WKR-P1-AUD-003)."""
    harness = ExecutorHarness.build(
        tmp_path,
        job_status=JobStatus.CANCEL_REQUESTED,
        aisle_status=AisleStatus.QUEUED,
    )
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.cancel_requested_at = harness.now
    harness.job_repo.save(job)
    executor = harness.make_executor()
    runner = RecordingPipelineRunner(executor._pipeline_runner, clock=FixedClock(harness.now))
    executor._pipeline_runner = runner
    spy = ExecutionSpy()
    spy.attach(executor)

    handled = executor.execute(harness.base_path, harness.job_id)

    assert handled is True
    assert runner.run_hybrid_pipeline_calls == 0
    assert spy.persist_calls == 0
    assert spy.recompute_calls == 0
    assert spy.artifact_put_calls == 0
    assert spy.mark_success_calls == 0
    assert spy.cancel_job_calls >= 1
    assert spy.cancel_job_and_aisle_calls == 0
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.CANCELED
    assert job.failure_code == "CANCELED"
    assert job.cancel_requested_at == harness.now
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.QUEUED
    inv = harness.inventory_repo.get_by_id(harness.inventory_id)
    assert inv is not None
    assert inv.status == InventoryStatus.PROCESSING


# --- Block 3: WKR-P1-T005 -----------------------------------------------------


def test_wkr_p1_t005_cancel_before_provider_checkpoint_skips_persist(tmp_path) -> None:
    """WKR-P1-T005: RUNNING job; cancel at pre_pipeline; provider path aborted."""
    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.STARTING)
    executor = harness.make_executor()
    runner = RecordingPipelineRunner(
        executor._pipeline_runner, clock=FixedClock(harness.now)
    )
    runner.arm_cancel_before_hybrid_run(job_repo=harness.job_repo, job_id=harness.job_id)
    executor._pipeline_runner = runner
    spy = ExecutionSpy()
    spy.attach(executor)

    handled = harness.run_with_mock_pipeline(executor)
    assert handled is True
    assert runner.run_hybrid_pipeline_calls == 1
    assert harness.pipeline_invocations == 0
    assert spy.persist_calls == 0
    assert spy.recompute_calls == 0
    assert spy.artifact_put_calls == 0
    assert spy.mark_success_calls == 0
    assert spy.cancel_job_and_aisle_calls >= 1
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.CANCELED
    assert job.failure_code == "CANCELED"
    assert len(harness.positions_for_job()) == 0
    log = harness.execution_log_text()
    assert "job.cancel_detected" in log or job.status == JobStatus.CANCELED


# --- Block 3: WKR-P1-T006 -----------------------------------------------------


def test_wkr_p1_t006_cancel_after_provider_before_persist_skips_domain_writes(
    tmp_path,
) -> None:
    """WKR-P1-T006: provider completes; post_pipeline cancel prevents persistence."""
    harness = ExecutorHarness.build(tmp_path)
    executor = harness.make_executor()
    runner = RecordingPipelineRunner(
        executor._pipeline_runner, clock=FixedClock(harness.now)
    )
    runner.arm_cancel_after_provider(job_repo=harness.job_repo, job_id=harness.job_id)
    executor._pipeline_runner = runner
    spy = ExecutionSpy()
    spy.attach(executor)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert runner.run_hybrid_pipeline_calls == 1
    assert harness.pipeline_invocations == 1
    assert spy.persist_calls == 0
    assert spy.recompute_calls == 0
    assert spy.artifact_put_calls == 0
    assert spy.mark_success_calls == 0
    assert spy.cancel_job_and_aisle_calls >= 1
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.CANCELED
    assert len(harness.positions_for_job()) == 0
    log = harness.execution_log_text()
    assert "job.cancel_detected" in log or job.status == JobStatus.CANCELED


# --- Block 3: WKR-P1-T006B ----------------------------------------------------


def test_wkr_p1_t006b_cancel_after_persist_stops_before_artifacts_not_mark_success(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WKR-P1-T006B: persist completes; pre_upload cancel prevents artifacts and success."""
    artifact_store = ArtifactUploadSpy()
    harness = ExecutorHarness.build(tmp_path, artifact_store=artifact_store)
    executor = harness.make_executor()
    spy = ExecutionSpy()
    spy.attach(executor, artifact_store=artifact_store)
    spied_persist = executor._persist_use_case.execute

    def persist_then_request_cancel(cmd):  # type: ignore[no-untyped-def]
        spied_persist(cmd)
        job = harness.job_repo.get_by_id(harness.job_id)
        assert job is not None
        job.status = JobStatus.CANCEL_REQUESTED
        job.cancel_requested_at = harness.now
        harness.job_repo.save(job)

    monkeypatch.setattr(executor._persist_use_case, "execute", persist_then_request_cancel)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert harness.pipeline_invocations == 1
    assert spy.persist_calls == 1
    assert spy.recompute_calls == 1
    assert spy.artifact_put_calls == 0
    assert spy.mark_success_calls == 0
    assert spy.fail_job_and_aisle_calls >= 1
    assert spy.cancel_job_and_aisle_calls == 0
    assert len(harness.positions_for_job()) == 2
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert "artifact" in (job.error_message or "").lower() or "canceled" in (
        job.error_message or ""
    ).lower()
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.FAILED


# --- Block 4: WKR-P1-T008 -----------------------------------------------------


def test_wkr_p1_t008_deepseek_rejects_multimodal_at_adapter_execute() -> None:
    """WKR-P1-T008: incompatible provider rejected at adapter execute (not job creation)."""
    import numpy as np

    adapter = DeepSeekSdkAdapter()
    settings = MagicMock()
    settings.deepseek_api_key = "sk-test"
    settings.deepseek_model = "deepseek-chat"
    settings.deepseek_api_base_url = "https://api.deepseek.com"
    settings.deepseek_request_timeout_sec = 30.0
    settings.deepseek_vision_max_image_side = 2048

    req = LLMRequest(
        job_id="job-ds",
        frames=[],
        frame_refs=["img-1"],
        prompt="analyze",
        schema_version="v2.1",
        metadata={"deepseek_model_name": "deepseek-chat"},
        frames_nd=[np.zeros((4, 4, 3), dtype=np.uint8)],
    )
    with pytest.raises(LLMProviderError) as exc_info:
        adapter.execute(req, settings)
    assert exc_info.value.code == "UNSUPPORTED_MULTIMODAL_PROVIDER"
