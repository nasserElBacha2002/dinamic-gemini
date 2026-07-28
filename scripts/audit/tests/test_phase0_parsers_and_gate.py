"""Unit tests for Phase 0 audit parsers and quality gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

AUDIT_DIR = Path(__file__).resolve().parents[1]
if str(AUDIT_DIR) not in sys.path:
    sys.path.insert(0, str(AUDIT_DIR))

from enforce_quality_gate import evaluate_gate  # noqa: E402
from lib.parsers import (  # noqa: E402
    parse_jest,
    parse_mypy,
    parse_npm_audit,
    parse_pytest,
    parse_ruff,
    parse_typescript,
    parse_vitest,
)
from lib.statuses import ToolStatus  # noqa: E402


@pytest.fixture
def tmp_report(tmp_path: Path):
    def _write(name: str, content: str, exit_code: int | None = None) -> Path:
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        if exit_code is not None:
            (tmp_path / f"{name}.exitcode").write_text(f"{exit_code}\n", encoding="utf-8")
        return path

    return _write


def test_pytest_clean(tmp_report):
    path = tmp_report(
        "pytest.txt",
        "===== 10 passed, 2 skipped in 1.2s =====\n",
        exit_code=0,
    )
    tr = parse_pytest(path)
    assert tr.status == ToolStatus.OK.value
    assert tr.metrics["passed"] == 10
    assert tr.exit_code == 0


def test_pytest_failed(tmp_report):
    path = tmp_report(
        "pytest.txt",
        "===== 2 failed, 8 passed, 1 skipped in 3.0s =====\n",
        exit_code=1,
    )
    tr = parse_pytest(path)
    assert tr.status == ToolStatus.FINDINGS.value
    assert tr.metrics["failed"] == 2


def test_pytest_collection_error(tmp_report):
    path = tmp_report(
        "pytest.txt",
        "ERROR collecting tests/foo.py\nImportError while importing test module\n",
        exit_code=2,
    )
    tr = parse_pytest(path)
    assert tr.status == ToolStatus.EXECUTION_ERROR.value


def test_pytest_empty(tmp_report):
    path = tmp_report("pytest.txt", "", exit_code=2)
    tr = parse_pytest(path)
    assert tr.status == ToolStatus.EXECUTION_ERROR.value


def test_pytest_missing(tmp_path: Path):
    tr = parse_pytest(tmp_path / "missing.txt")
    assert tr.status == ToolStatus.NOT_RUN.value


def test_ruff_clean(tmp_report):
    path = tmp_report("ruff.txt", "All checks passed!\n", exit_code=0)
    tr = parse_ruff(path)
    assert tr.status == ToolStatus.OK.value


def test_ruff_findings(tmp_report):
    path = tmp_report("ruff.txt", "Found 3 errors.\n[*] 2 fixable with --fix.\n", exit_code=1)
    tr = parse_ruff(path)
    assert tr.status == ToolStatus.FINDINGS.value
    assert tr.metrics["issues"] == 3


def test_ruff_unavailable(tmp_report):
    path = tmp_report("ruff.txt", "Ruff no instalado en el entorno actual.\n", exit_code=127)
    tr = parse_ruff(path)
    assert tr.status == ToolStatus.NOT_AVAILABLE.value


def test_mypy_success(tmp_report):
    path = tmp_report("mypy.txt", "Success: no issues found in 10 source files\n", exit_code=0)
    tr = parse_mypy(path)
    assert tr.status == ToolStatus.OK.value


def test_mypy_errors(tmp_report):
    path = tmp_report("mypy.txt", "Found 4 errors in 2 files (checked 10 source files)\n", exit_code=1)
    tr = parse_mypy(path)
    assert tr.status == ToolStatus.FINDINGS.value
    assert tr.metrics["errors"] == 4


def test_typescript_exit_zero_ignores_noise(tmp_report):
    # Numbers that look like errors must not invent failures when exit=0.
    path = tmp_report(
        "tsc.txt",
        "npm warn something\nerror TS0000 appears in a comment example only if counted blindly\n",
        exit_code=0,
    )
    tr = parse_typescript(path)
    assert tr.status == ToolStatus.OK.value
    assert tr.metrics.get("ts_errors", 0) == 0


def test_typescript_found_summary(tmp_report):
    path = tmp_report(
        "tsc.txt",
        "src/a.ts(1,1): error TS2322: Type 'string' is not assignable...\nFound 2 errors in 1 file.\n",
        exit_code=1,
    )
    tr = parse_typescript(path)
    assert tr.status == ToolStatus.FINDINGS.value
    assert tr.metrics["ts_errors"] == 2


def test_typescript_real_errors_without_summary(tmp_report):
    path = tmp_report(
        "tsc.txt",
        "src/a.ts(1,1): error TS2322: bad\nsrc/b.ts(2,2): error TS2304: missing\n",
        exit_code=1,
    )
    tr = parse_typescript(path)
    assert tr.status == ToolStatus.FINDINGS.value
    assert tr.metrics["ts_errors"] == 2


def test_vitest_green(tmp_report):
    path = tmp_report(
        "vitest.txt",
        " Test Files  10 passed (10)\n      Tests  1217 passed (1217)\n",
        exit_code=0,
    )
    tr = parse_vitest(path)
    assert tr.status == ToolStatus.OK.value
    assert tr.metrics["passed_tests"] == 1217


def test_vitest_failed(tmp_report):
    path = tmp_report(
        "vitest.txt",
        " Test Files  1 failed | 9 passed (10)\n      Tests  2 failed | 100 passed (102)\n",
        exit_code=1,
    )
    tr = parse_vitest(path)
    assert tr.status == ToolStatus.FINDINGS.value
    assert tr.metrics["failed_tests"] == 2


def test_vitest_no_summary_not_ok(tmp_report):
    path = tmp_report("vitest.txt", "something went wrong starting vite\n", exit_code=0)
    tr = parse_vitest(path)
    assert tr.status == ToolStatus.PARSE_ERROR.value


def test_jest_green(tmp_report):
    path = tmp_report(
        "jest.txt",
        "Test Suites: 5 passed, 5 total\nTests:       159 passed, 159 total\n",
        exit_code=0,
    )
    tr = parse_jest(path)
    assert tr.status == ToolStatus.OK.value
    assert tr.metrics["passed"] == 159


def test_npm_audit_zero(tmp_report):
    path = tmp_report(
        "npm.json",
        json.dumps({"metadata": {"vulnerabilities": {"total": 0, "high": 0, "critical": 0}}}),
        exit_code=0,
    )
    tr = parse_npm_audit(path)
    assert tr.status == ToolStatus.OK.value


def test_npm_audit_high(tmp_report):
    path = tmp_report(
        "npm.json",
        json.dumps(
            {
                "metadata": {
                    "vulnerabilities": {
                        "info": 0,
                        "low": 1,
                        "moderate": 2,
                        "high": 3,
                        "critical": 0,
                        "total": 6,
                    }
                }
            }
        ),
        exit_code=1,
    )
    tr = parse_npm_audit(path)
    assert tr.status == ToolStatus.FINDINGS.value
    assert tr.metrics["high"] == 3
    assert tr.severity == "high"


def test_npm_audit_invalid_json(tmp_report):
    path = tmp_report("npm.json", "not-json", exit_code=1)
    tr = parse_npm_audit(path)
    assert tr.status == ToolStatus.PARSE_ERROR.value


def test_npm_audit_network_error(tmp_report):
    path = tmp_report("npm.json", "npm ERR! network fetch failed ENOTFOUND\n", exit_code=1)
    tr = parse_npm_audit(path)
    assert tr.status == ToolStatus.EXECUTION_ERROR.value


def _base_status() -> dict:
    def ok_tool(extra_metrics=None):
        return {
            "status": "OK",
            "severity": "none",
            "metrics": extra_metrics or {},
            "report": "x",
            "observation": "",
            "exit_code": 0,
            "error": None,
        }

    return {
        "schema_version": 2,
        "run_id": "test-run",
        "overall_status": "ok",
        "max_severity": "none",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "areas": {
            "backend": {
                "status": "OK",
                "tools": {
                    "pytest": ok_tool({"passed": 10, "failed": 0}),
                    "ruff": ok_tool({"issues": 0}),
                    "mypy": ok_tool({"errors": 0}),
                    "bandit": ok_tool({"high": 0}),
                    "pip-audit": ok_tool({"total": 0}),
                },
                "highlights": {"pytest_failed": 0},
            },
            "frontend": {
                "status": "OK",
                "tools": {
                    "vitest": ok_tool({"passed_tests": 5, "failed_tests": 0}),
                    "typecheck": ok_tool({"ts_errors": 0}),
                    "eslint": ok_tool({"errors": 0, "warnings": 0}),
                    "npm_audit": ok_tool({"total": 0}),
                },
                "highlights": {"vitest_failed_tests": 0},
            },
            "mobile": {
                "status": "OK",
                "tools": {
                    "jest": ok_tool({"passed": 9, "failed": 0}),
                    "typecheck": ok_tool({"ts_errors": 0}),
                    "eslint": ok_tool({"errors": 0, "warnings": 0}),
                    "npm_audit": ok_tool({"total": 0}),
                },
                "highlights": {"jest_failed": 0},
            },
        },
    }


def test_gate_pass():
    passed, reasons, _ = evaluate_gate(_base_status())
    assert passed is True
    assert reasons == []


def test_gate_pytest_not_run():
    status = _base_status()
    status["areas"]["backend"]["tools"]["pytest"] = {
        "status": "NOT_RUN",
        "severity": "info",
        "metrics": {},
        "report": "x",
        "observation": "missing",
        "exit_code": None,
        "error": None,
    }
    passed, reasons, _ = evaluate_gate(status)
    assert passed is False
    assert any("not executed" in r for r in reasons)


def test_gate_parse_error():
    status = _base_status()
    status["areas"]["frontend"]["tools"]["typecheck"] = {
        "status": "PARSE_ERROR",
        "severity": "medium",
        "metrics": {},
        "report": "x",
        "observation": "",
        "exit_code": 1,
        "error": "broken",
    }
    passed, reasons, _ = evaluate_gate(status)
    assert passed is False
    assert any("PARSE_ERROR" in r for r in reasons)


def test_gate_mobile_missing():
    status = _base_status()
    del status["areas"]["mobile"]
    passed, reasons, _ = evaluate_gate(status)
    assert passed is False
    assert any("mobile" in r.lower() for r in reasons)
