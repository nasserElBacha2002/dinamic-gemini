from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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

    monkeypatch.setattr(run_worker, "worker_loop", fake_worker_loop)
    run_worker.main()

    assert captured["base"] == Path("output/custom-worker")


def test_run_worker_main_runs_single_job_when_job_id_is_provided(monkeypatch) -> None:
    captured = {"job_id": None}

    monkeypatch.setattr(
        run_worker,
        "load_settings",
        lambda: SimpleNamespace(output_dir="output/custom-worker"),
    )
    monkeypatch.setattr(run_worker, "worker_loop", lambda _base: (_ for _ in ()).throw(AssertionError("worker_loop should not run")))
    monkeypatch.setattr(run_worker, "run_job", lambda _base, job_id: captured.__setitem__("job_id", job_id))

    run_worker.main(["--job-id", "job-123", "--execution-id", "exec-123"])

    assert captured["job_id"] == "job-123"

