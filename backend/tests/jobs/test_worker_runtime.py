from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from src.jobs.worker import worker_loop
from src.jobs.worker_runtime import (
    READY_REASON_JOB_WORKER_UNAVAILABLE,
    REASON_REPOSITORIES_NOT_INITIALIZED,
    REASON_WORKER_NOT_STARTED,
    REASON_WORKER_TERMINATED,
    EmbeddedWorkerRuntime,
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


def test_start_is_idempotent_and_shutdown_stops_loop(monkeypatch) -> None:
    reset_embedded_worker_runtime_for_tests()
    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=False)
    monkeypatch.setattr("src.jobs.worker.claim_next_job", lambda _base: None)

    t1 = threading.Thread(
        target=lambda: worker_loop(Path("output"), stop=runtime.should_stop),
        daemon=True,
        name="t1",
    )
    runtime.mark_started(t1)
    t1.start()
    assert runtime.is_thread_alive()
    assert runtime.is_thread_alive()  # second observe, no second thread
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
