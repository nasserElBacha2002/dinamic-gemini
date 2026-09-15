from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from src.jobs.claim_cycle import WorkerClaimCycleResult, WorkerClaimCycleStatus
from src.jobs.worker import worker_loop
from src.jobs.worker_runtime import (
    READY_REASON_JOB_WORKER_UNAVAILABLE,
    REASON_REPOSITORIES_NOT_INITIALIZED,
    REASON_WORKER_NOT_STARTED,
    REASON_WORKER_STARTING,
    REASON_WORKER_STOPPING,
    REASON_WORKER_TERMINATED,
    EmbeddedWorkerRuntime,
    WorkerLifecyclePhase,
    get_embedded_worker_runtime,
    reset_embedded_worker_runtime_for_tests,
)


def test_unavailable_log_is_rate_limited(caplog) -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    with caplog.at_level(logging.ERROR):
        runtime.mark_unavailable(REASON_REPOSITORIES_NOT_INITIALIZED)
        runtime.mark_unavailable(REASON_REPOSITORIES_NOT_INITIALIZED)
        runtime.mark_unavailable(REASON_REPOSITORIES_NOT_INITIALIZED)
    assert caplog.text.count("job_worker_unavailable") == 1


def test_recovery_logs_downtime(caplog) -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    with caplog.at_level(logging.INFO):
        runtime.mark_unavailable(REASON_REPOSITORIES_NOT_INITIALIZED)
        runtime.mark_cycle_ok()
    assert "job_worker_recovered downtime_seconds=" in caplog.text
    assert runtime.snapshot().unavailable_reason is None
    assert runtime.snapshot().last_success_at is not None


def test_readiness_problem_when_required_but_not_started() -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=True)
    assert runtime.readiness_problem() == (
        READY_REASON_JOB_WORKER_UNAVAILABLE,
        REASON_WORKER_NOT_STARTED,
    )
    runtime.configure(required=False, sql_mode=False)
    assert runtime.readiness_problem() is None


def test_dedicated_worker_mode_does_not_require_local_thread() -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=False, sql_mode=True)
    assert runtime.readiness_problem() is None
    assert runtime.snapshot().worker_available is True


def test_readiness_problem_when_thread_dies() -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=True)

    def _noop() -> None:
        return None

    thread = threading.Thread(target=_noop, daemon=True)
    runtime.mark_started(thread)
    thread.start()
    thread.join(timeout=2.0)
    problem = runtime.readiness_problem()
    assert problem == (READY_REASON_JOB_WORKER_UNAVAILABLE, REASON_WORKER_TERMINATED)


def test_thread_alive_without_first_cycle_ready_is_503() -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=True)

    def _block() -> None:
        while not runtime.should_stop():
            time.sleep(0.01)

    thread = threading.Thread(target=_block, daemon=True)
    runtime.mark_started(thread)
    thread.start()
    assert runtime.snapshot().phase is WorkerLifecyclePhase.STARTING
    assert runtime.readiness_problem() == (
        READY_REASON_JOB_WORKER_UNAVAILABLE,
        REASON_WORKER_STARTING,
    )
    assert runtime.snapshot().worker_available is False
    runtime.request_stop()
    runtime.join(timeout_sec=2.0)


def test_first_idle_healthy_makes_ready() -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=True)

    def _block() -> None:
        while not runtime.should_stop():
            time.sleep(0.01)

    thread = threading.Thread(target=_block, daemon=True)
    runtime.mark_started(thread)
    thread.start()
    assert runtime.readiness_problem()[1] == REASON_WORKER_STARTING
    runtime.mark_cycle_ok()
    assert runtime.snapshot().phase is WorkerLifecyclePhase.READY
    assert runtime.readiness_problem() is None
    assert runtime.snapshot().worker_available is True
    runtime.request_stop()
    runtime.join(timeout_sec=2.0)


def test_stopping_returns_503_without_unexpected_termination() -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=True)

    def _block() -> None:
        while not runtime.should_stop():
            time.sleep(0.01)

    thread = threading.Thread(target=_block, daemon=True)
    runtime.mark_started(thread)
    thread.start()
    runtime.mark_cycle_ok()
    assert runtime.readiness_problem() is None
    runtime.request_stop()
    problem = runtime.readiness_problem()
    assert problem == (
        READY_REASON_JOB_WORKER_UNAVAILABLE,
        REASON_WORKER_STOPPING,
    )
    runtime.join(timeout_sec=2.0)
    runtime.mark_thread_finished(unexpected=False)
    assert runtime.snapshot().unexpected_termination_count == 0
    assert runtime.readiness_problem() == (
        READY_REASON_JOB_WORKER_UNAVAILABLE,
        REASON_WORKER_STOPPING,
    )


def test_unexpected_thread_death_increments_counter() -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=True)

    def _noop() -> None:
        return None

    thread = threading.Thread(target=_noop, daemon=True)
    runtime.mark_started(thread)
    thread.start()
    thread.join(timeout=2.0)
    runtime.mark_thread_finished(unexpected=True)
    assert runtime.snapshot().unexpected_termination_count == 1
    assert runtime.readiness_problem() == (
        READY_REASON_JOB_WORKER_UNAVAILABLE,
        REASON_WORKER_TERMINATED,
    )


def test_start_is_idempotent_and_shutdown_stops_loop(monkeypatch) -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=False)

    def idle(_base: Path) -> WorkerClaimCycleResult:
        return WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.IDLE_HEALTHY, detail="idle"
        )

    monkeypatch.setattr("src.jobs.worker.claim_next_job_cycle", idle)

    t1 = threading.Thread(
        target=lambda: worker_loop(Path("output"), stop=runtime.should_stop),
        daemon=True,
        name="t1",
    )
    runtime.mark_started(t1)
    t1.start()
    assert runtime.is_thread_alive()
    # Observing again must not imply a second thread was created.
    assert runtime.is_thread_alive()
    deadline = time.monotonic() + 2.0
    while runtime.snapshot().phase is not WorkerLifecyclePhase.READY:
        if time.monotonic() > deadline:
            break
        time.sleep(0.02)
    assert runtime.snapshot().phase is WorkerLifecyclePhase.READY
    runtime.request_stop()
    runtime.join(timeout_sec=3.0)
    assert not t1.is_alive()


def test_isolated_runtime_instances_do_not_share_stop_event() -> None:
    a = EmbeddedWorkerRuntime()
    b = EmbeddedWorkerRuntime()
    a.request_stop()
    assert a.should_stop()
    assert not b.should_stop()
    time.sleep(0.01)


def test_unexpected_loop_exception_marks_unavailable(monkeypatch) -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=True)
    stop_state = {"n": 0}

    def boom_claim(_base: Path):
        raise RuntimeError("boom")

    def stop_after() -> bool:
        stop_state["n"] += 1
        return stop_state["n"] > 1

    monkeypatch.setattr("src.jobs.worker.claim_next_job_cycle", boom_claim)
    monkeypatch.setattr("src.jobs.worker.time.sleep", lambda _s: None)
    worker_loop(Path("output"), stop=stop_after)
    assert runtime.snapshot().unavailable_reason == "claim_loop_exception"
    assert runtime.readiness_problem() is not None


def test_observability_dict_exposes_counters() -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.mark_unavailable(REASON_REPOSITORIES_NOT_INITIALIZED)
    runtime.mark_cycle_ok()
    obs = runtime.observability_dict()
    assert obs["recovery_count"] == 1
    assert obs["worker_unavailable_reason"] is None
    assert obs["last_success_at"] is not None
    assert obs["failure_count"] == 1
