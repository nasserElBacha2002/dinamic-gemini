from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.infrastructure.services.on_demand_worker_launch_service import OnDemandWorkerLaunchService


def test_build_command_defaults_to_current_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKER_ON_DEMAND_COMMAND", raising=False)

    command = OnDemandWorkerLaunchService()._build_command()

    assert len(command) == 3
    assert command[1:] == ["-m", "src.jobs.run_worker"]


def test_build_command_accepts_json_array_for_paths_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = ["/Users/me/My Env/bin/python", "-m", "src.jobs.run_worker"]
    monkeypatch.setenv("WORKER_ON_DEMAND_COMMAND", json.dumps(expected))

    command = OnDemandWorkerLaunchService()._build_command()

    assert command == expected


def test_build_command_keeps_shell_style_string_for_backward_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "WORKER_ON_DEMAND_COMMAND",
        "\"/Users/me/My Env/bin/python\" -m src.jobs.run_worker",
    )

    command = OnDemandWorkerLaunchService()._build_command()

    assert command == ["/Users/me/My Env/bin/python", "-m", "src.jobs.run_worker"]


def test_launch_uses_json_command_without_splitting_paths_with_spaces(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 12345

        def poll(self) -> None:
            return None

    def fake_popen(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        return FakeProcess()

    monkeypatch.setenv(
        "WORKER_ON_DEMAND_COMMAND",
        json.dumps(["/Users/me/My Env/bin/python", "-m", "src.jobs.run_worker"]),
    )
    monkeypatch.setattr(
        "src.infrastructure.services.on_demand_worker_launch_service.load_settings",
        lambda: SimpleNamespace(output_dir=str(tmp_path)),
    )
    monkeypatch.setattr(
        "src.infrastructure.services.on_demand_worker_launch_service.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "src.infrastructure.services.on_demand_worker_launch_service.time.sleep",
        lambda _: None,
    )

    service = OnDemandWorkerLaunchService()
    execution_id = service.launch("job-123")

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:3] == ["/Users/me/My Env/bin/python", "-m", "src.jobs.run_worker"]
    assert command[-4:-2] == ["--job-id", "job-123"]
    assert command[-2] == "--execution-id"
    assert command[-1] == execution_id
