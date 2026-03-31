from __future__ import annotations

from pathlib import Path

from src.jobs import run_worker_dev


def test_backend_root_points_to_backend_directory() -> None:
    expected = Path(__file__).resolve().parents[2]
    assert run_worker_dev.backend_root() == expected


def test_main_watches_backend_and_runs_standard_worker(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def _fake_run_process(*paths, target, debounce):  # type: ignore[no-untyped-def]
        calls["paths"] = paths
        calls["target"] = target
        calls["debounce"] = debounce

    monkeypatch.setattr(run_worker_dev, "run_process", _fake_run_process)

    run_worker_dev.main()

    assert calls["paths"] == (str(run_worker_dev.backend_root()),)
    assert calls["target"] is run_worker_dev.run_worker_once
    assert calls["debounce"] == 500
