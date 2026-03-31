from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.modules.setdefault("cv2", SimpleNamespace())
sys.modules.setdefault("numpy", SimpleNamespace())

from src.jobs import run_worker


def test_run_worker_main_uses_settings_output_dir(monkeypatch) -> None:
    captured = {"base": None}

    monkeypatch.setattr(
        run_worker,
        "load_settings",
        lambda: SimpleNamespace(output_dir="output/custom-worker"),
    )

    def fake_worker_loop(base: Path) -> None:
        captured["base"] = base

    monkeypatch.setattr(
        run_worker,
        "_import_worker_runtime",
        lambda: (lambda *_args, **_kwargs: None, fake_worker_loop),
    )
    run_worker.main()

    assert captured["base"] == Path("output/custom-worker")


def test_run_worker_main_runs_single_job_when_job_id_is_provided(monkeypatch) -> None:
    captured = {"job_id": None}

    monkeypatch.setattr(
        run_worker,
        "load_settings",
        lambda: SimpleNamespace(output_dir="output/custom-worker"),
    )
    monkeypatch.setattr(
        run_worker,
        "_import_worker_runtime",
        lambda: (
            lambda _base, job_id, execution_id=None: captured.update(job_id=job_id, execution_id=execution_id),
            lambda _base: (_ for _ in ()).throw(AssertionError("worker_loop should not run")),
        ),
    )

    run_worker.main(["--job-id", "job-123", "--execution-id", "exec-123"])

    assert captured["job_id"] == "job-123"
    assert captured["execution_id"] == "exec-123"


def test_run_worker_main_uses_sys_argv_when_argv_is_none(monkeypatch) -> None:
    captured = {"job_id": None, "execution_id": None}

    monkeypatch.setattr(
        run_worker,
        "load_settings",
        lambda: SimpleNamespace(output_dir="output/custom-worker"),
    )
    monkeypatch.setattr(run_worker, "_log_storage_provider", lambda: None)
    monkeypatch.setattr(run_worker, "_log_sql_worker_health", lambda: None)
    monkeypatch.setattr(run_worker, "append_worker_bootstrap_event", lambda **kwargs: None)
    monkeypatch.setattr(run_worker, "checkpoint_v3_job_bootstrap", lambda **kwargs: None)
    monkeypatch.setattr(
        run_worker,
        "_import_worker_runtime",
        lambda: (
            lambda _base, job_id, execution_id=None: captured.update(job_id=job_id, execution_id=execution_id),
            lambda _base: (_ for _ in ()).throw(AssertionError("worker_loop should not run")),
        ),
    )
    monkeypatch.setattr(
        run_worker.sys,
        "argv",
        ["python", "--job-id", "job-from-sys-argv", "--execution-id", "exec-from-sys-argv"],
    )

    run_worker.main()

    assert captured["job_id"] == "job-from-sys-argv"
    assert captured["execution_id"] == "exec-from-sys-argv"


def test_run_worker_main_emits_bootstrap_events_and_checkpoint_for_single_job(monkeypatch) -> None:
    captured: dict[str, object] = {"events": [], "checkpoints": []}

    monkeypatch.setattr(
        run_worker,
        "load_settings",
        lambda: SimpleNamespace(output_dir="output/custom-worker"),
    )
    monkeypatch.setattr(run_worker, "_log_storage_provider", lambda: None)
    monkeypatch.setattr(run_worker, "_log_sql_worker_health", lambda: None)
    monkeypatch.setattr(
        run_worker,
        "append_worker_bootstrap_event",
        lambda **kwargs: captured["events"].append(kwargs["event"]),
    )
    monkeypatch.setattr(
        run_worker,
        "checkpoint_v3_job_bootstrap",
        lambda **kwargs: captured["checkpoints"].append(kwargs["substep"]),
    )
    monkeypatch.setattr(
        run_worker,
        "_import_worker_runtime",
        lambda: (
            lambda _base, job_id, execution_id=None: captured.update(job_id=job_id, execution_id=execution_id),
            lambda _base: None,
        ),
    )

    run_worker.main(["--job-id", "job-123", "--execution-id", "exec-123"])

    assert captured["job_id"] == "job-123"
    assert captured["execution_id"] == "exec-123"
    assert captured["events"] == [
        "worker.process_started",
        "worker.args_parsed",
        "worker.single_job_mode_entered",
    ]
    assert captured["checkpoints"] == [
        "args_parsed",
        "single_job_mode_entered",
    ]


def test_run_worker_main_marks_failed_when_single_job_bootstrap_raises(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        run_worker,
        "load_settings",
        lambda: SimpleNamespace(output_dir="output/custom-worker"),
    )
    monkeypatch.setattr(run_worker, "_log_storage_provider", lambda: None)
    monkeypatch.setattr(run_worker, "_log_sql_worker_health", lambda: None)
    monkeypatch.setattr(run_worker, "append_worker_bootstrap_event", lambda **kwargs: None)
    monkeypatch.setattr(run_worker, "checkpoint_v3_job_bootstrap", lambda **kwargs: None)
    monkeypatch.setattr(
        run_worker,
        "fail_v3_job_bootstrap",
        lambda **kwargs: captured.update(kwargs),
    )
    monkeypatch.setattr(
        run_worker,
        "_import_worker_runtime",
        lambda: (
            lambda _base, _job_id, execution_id=None: (_ for _ in ()).throw(RuntimeError("boom")),
            lambda _base: None,
        ),
    )

    try:
        run_worker.main(["--job-id", "job-123", "--execution-id", "exec-123"])
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert str(exc) == "boom"

    assert captured["job_id"] == "job-123"
    assert captured["execution_id"] == "exec-123"
    assert captured["substep"] == "single_job_mode_failed"
    assert captured["error_message"] == "boom"

