"""Unit tests for debug_job UUID entity resolution helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "debug_job.py"


def _load_debug_job():
    spec = importlib.util.spec_from_file_location("debug_job_under_test", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeCursor:
    def __init__(self, responses: list[list[tuple] | None]):
        self._responses = list(responses)
        self.description = [("id",), ("status",), ("target_type",), ("target_id",), ("execution_id",), ("created_at",), ("finished_at",)]
        self._rows: list[tuple] = []

    def execute(self, sql: str, params=None) -> None:  # noqa: ANN001
        self._rows = list(self._responses.pop(0) or [])
        sql_l = sql.lower()
        if "from aisles" in sql_l:
            self.description = [("id",), ("inventory_id",), ("code",), ("status",)]
        elif "from inventories" in sql_l:
            self.description = [("id",), ("name",), ("status",)]
        elif "from source_assets" in sql_l:
            self.description = [("id",), ("aisle_id",), ("storage_key",)]
        elif "from inventory_jobs" in sql_l and "target_type" in sql_l:
            self.description = [
                ("id",),
                ("status",),
                ("identification_mode",),
                ("execution_strategy",),
                ("created_at",),
                ("started_at",),
                ("finished_at",),
                ("failure_code",),
            ]
        else:
            self.description = [
                ("id",),
                ("status",),
                ("target_type",),
                ("target_id",),
                ("execution_id",),
                ("created_at",),
                ("finished_at",),
            ]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def test_resolve_valid_job_id() -> None:
    mod = _load_debug_job()
    cur = _FakeCursor(
        [
            [("job-1", "SUCCEEDED", "aisle", "aisle-1", "exec-1", None, None)],  # job
            [],  # aisle
            [],  # inventory
            [],  # asset
        ]
    )
    resolved = mod.resolve_uuid_entity(cur, "job-1")
    assert resolved["kinds"] == ["job"]
    assert resolved["job"]["id"] == "job-1"


def test_resolve_aisle_id_not_job() -> None:
    mod = _load_debug_job()
    cur = _FakeCursor(
        [
            [],  # job
            [("aisle-1", "inv-1", "A1", "active")],  # aisle
            [],  # inventory
            [],  # asset
        ]
    )
    resolved = mod.resolve_uuid_entity(cur, "aisle-1")
    assert "aisle" in resolved["kinds"]
    assert "job" not in resolved["kinds"]


def test_print_wrong_entity_suggests_latest_job(capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_debug_job()
    cur = _FakeCursor(
        [
            [
                (
                    "job-latest",
                    "SUCCEEDED",
                    "CODE_SCAN_ONLY",
                    "CODE_SCAN",
                    None,
                    None,
                    None,
                    None,
                )
            ]
        ]
    )
    resolved = {
        "uuid": "aisle-1",
        "kinds": ["aisle"],
        "aisle": {"id": "aisle-1", "inventory_id": "inv-1", "code": "P1"},
    }
    rc = mod._print_wrong_entity_as_job(cur, resolved, "aisle-1")
    err = capsys.readouterr().err
    assert rc == 2
    assert "UUID no corresponde a Job" in err
    assert "Aisle ID" in err
    assert "job-latest" in err


def test_unknown_uuid_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_debug_job()
    cur = _FakeCursor([[]])  # no latest jobs query needed
    resolved = {"uuid": "missing", "kinds": []}
    rc = mod._print_wrong_entity_as_job(cur, resolved, "missing")
    err = capsys.readouterr().err
    assert rc == 1
    assert "No encontrado" in err


def test_infer_observability_generation_phase_timed() -> None:
    mod = _load_debug_job()
    events = [
        {
            "event_type": "asset.source_loaded",
            "metadata_json": {"source_load_ms": 3000, "observability_generation": "phase-timed"},
        },
        {"event_type": "code_scan.decode_started", "metadata_json": {"timeout_scope": "decode"}},
    ]
    assert mod._infer_observability_generation(events) == "phase-timed"


def test_infer_observability_generation_legacy() -> None:
    mod = _load_debug_job()
    events = [{"event_type": "code_scan.asset_started", "metadata_json": {}}]
    assert mod._infer_observability_generation(events) == "legacy"
