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

