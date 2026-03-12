"""Tests for execution log hardening (payload sanitization, resilient write)."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.pipeline.execution_log import (
    ExecutionLogWriter,
    _sanitize_payload,
    read_execution_log,
    read_last_stage_error,
)


def test_sanitize_payload_datetime_path_exception():
    """Non-JSON-serializable values are stringified so serialization never fails."""
    payload = {
        "ts": datetime.now(timezone.utc),
        "path": Path("/tmp/foo"),
        "err": ValueError("oops"),
        "nested": {"x": Path("/a/b")},
    }
    out = _sanitize_payload(payload)
    assert out is not None
    assert isinstance(out["ts"], str)
    assert isinstance(out["path"], str)
    assert "oops" in str(out["err"])
    assert isinstance(out["nested"]["x"], str)
    line = json.dumps({"payload": out}, ensure_ascii=False)
    json.loads(line)


def test_append_with_bad_payload_writes_fallback():
    """Writer appends a line even when payload would break raw json.dumps."""
    with tempfile.TemporaryDirectory() as d:
        run_dir = Path(d)
        w = ExecutionLogWriter(run_dir)
        w.append("Test", "info", "hello", {"dt": datetime.now(timezone.utc), "p": Path("/x")})
        w.append("Test", "error", "fail", {"e": ValueError("x")})
        events = read_execution_log(run_dir)
        assert len(events) == 2
        assert events[0]["message"] == "hello"
        assert "payload" in events[0]
        assert events[1]["message"] == "fail"


def test_read_execution_log_empty_dir():
    """Missing file returns empty list."""
    with tempfile.TemporaryDirectory() as d:
        assert read_execution_log(Path(d)) == []


def test_read_last_stage_error_missing():
    """Missing file returns None."""
    with tempfile.TemporaryDirectory() as d:
        assert read_last_stage_error(Path(d)) is None


def test_write_last_stage_error_truncated():
    """Long error message is truncated to 2048."""
    with tempfile.TemporaryDirectory() as d:
        w = ExecutionLogWriter(Path(d))
        long_msg = "x" * 3000
        w.write_last_stage_error("Stage", long_msg)
        out = read_last_stage_error(Path(d))
        assert out is not None
        assert len(out) == 2048
