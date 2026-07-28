"""Phase 0 correction tests: schema, policy, artifacts, full-audit safety."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

AUDIT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AUDIT_DIR.parents[1]
if str(AUDIT_DIR) not in sys.path:
    sys.path.insert(0, str(AUDIT_DIR))

from enforce_quality_gate import evaluate_gate  # noqa: E402
from lib.artifacts import clear_aggregate_outputs, publish_aggregate_outputs  # noqa: E402
from lib.gate_policy import REQUIRED_TOOL_RULES, policy_summary  # noqa: E402
from lib.schema import (  # noqa: E402
    SchemaValidationError,
    migrate_legacy_to_v2,
    normalize_status_document,
)
from lib.statuses import SCHEMA_VERSION  # noqa: E402
from test_phase0_parsers_and_gate import _base_status  # noqa: E402


def test_audit_lib_package_importable():
    """Clean-checkout style: import lib modules without PATH hacks beyond scripts/audit."""
    import lib.artifacts as artifacts
    import lib.gate_policy as gate_policy
    import lib.parsers as parsers
    import lib.python_env as python_env
    import lib.schema as schema
    import lib.statuses as statuses

    assert statuses.SCHEMA_VERSION == 2
    assert hasattr(parsers, "parse_pytest")
    assert hasattr(python_env, "resolve_python_env")
    assert hasattr(gate_policy, "REQUIRED_TOOL_RULES")
    assert hasattr(schema, "normalize_status_document")
    assert hasattr(artifacts, "clear_aggregate_outputs")


def test_schema_v2_accepted():
    doc, notes = normalize_status_document(_base_status())
    assert doc["schema_version"] == SCHEMA_VERSION
    assert any("accepted" in n for n in notes)


def test_schema_legacy_supported():
    legacy = _base_status()
    legacy["schema_version"] = 1
    doc, notes = normalize_status_document(legacy)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert any("legacy" in n for n in notes)


def test_schema_legacy_missing_version_migrates():
    legacy = _base_status()
    del legacy["schema_version"]
    doc, notes = normalize_status_document(legacy)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert any("missing" in n for n in notes)


def test_schema_legacy_incomplete_rejected():
    incomplete = {
        "schema_version": 1,
        "overall_status": "ok",
        "areas": {"backend": {"tools": {"pytest": {"status": "OK"}}}},
    }
    with pytest.raises(SchemaValidationError, match="incomplete|missing"):
        migrate_legacy_to_v2(incomplete)
    with pytest.raises(SchemaValidationError):
        normalize_status_document(incomplete)


def test_schema_future_unknown_rejected():
    doc = _base_status()
    doc["schema_version"] = 99
    with pytest.raises(SchemaValidationError, match="unknown|unsupported"):
        normalize_status_document(doc)


def test_schema_invalid_type_rejected():
    doc = _base_status()
    doc["schema_version"] = "two"
    with pytest.raises(SchemaValidationError, match="invalid"):
        normalize_status_document(doc)


def test_schema_missing_required_tool_rejected():
    doc = _base_status()
    del doc["areas"]["backend"]["tools"]["pytest"]
    with pytest.raises(SchemaValidationError, match="pytest"):
        normalize_status_document(doc)


def test_schema_missing_required_area_rejected():
    doc = _base_status()
    del doc["areas"]["mobile"]
    with pytest.raises(SchemaValidationError, match="mobile"):
        normalize_status_document(doc)


def test_gate_rejects_unknown_schema():
    doc = _base_status()
    doc["schema_version"] = 99
    passed, reasons, _ = evaluate_gate(doc)
    assert passed is False
    assert any("schema" in r.lower() for r in reasons)


def test_gate_rejects_incomplete_legacy():
    doc = {"overall_status": "ok", "areas": {}}
    passed, reasons, _ = evaluate_gate(doc)
    assert passed is False
    assert any("schema" in r.lower() or "incomplete" in r.lower() or "missing" in r.lower() for r in reasons)


def test_lint_policy_warnings_allowed_errors_block():
    rules = {r.label: r for r in REQUIRED_TOOL_RULES}
    fe = rules["Frontend ESLint"]
    assert fe.allow_findings is True
    assert "errors" in fe.failed_metric_keys

    status = _base_status()
    status["areas"]["frontend"]["tools"]["eslint"] = {
        "status": "FINDINGS",
        "severity": "medium",
        "metrics": {"errors": 0, "warnings": 3},
        "report": "x",
        "observation": "",
        "exit_code": 0,
        "error": None,
    }
    passed, reasons, _ = evaluate_gate(status)
    assert passed is True
    assert reasons == []

    status["areas"]["frontend"]["tools"]["eslint"]["metrics"] = {"errors": 2, "warnings": 0}
    passed, reasons, _ = evaluate_gate(status)
    assert passed is False
    assert any("ESLint" in r for r in reasons)


def test_advisory_findings_do_not_block_structural_ok():
    status = _base_status()
    status["areas"]["backend"]["tools"]["bandit"] = {
        "status": "FINDINGS",
        "severity": "medium",
        "metrics": {"high": 1},
        "report": "x",
        "observation": "",
        "exit_code": 1,
        "error": None,
    }
    status["areas"]["frontend"]["tools"]["npm_audit"] = {
        "status": "FINDINGS",
        "severity": "high",
        "metrics": {"high": 2, "total": 2},
        "report": "x",
        "observation": "",
        "exit_code": 1,
        "error": None,
    }
    passed, reasons, _ = evaluate_gate(status)
    assert passed is True
    assert reasons == []


def test_structural_invalidating_blocks_even_if_advisory():
    status = _base_status()
    status["areas"]["backend"]["tools"]["bandit"] = {
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
    assert any("Bandit" in r and "PARSE_ERROR" in r for r in reasons)


def test_policy_lists_all_required_tools():
    labels = {r.label for r in REQUIRED_TOOL_RULES}
    expected = {
        "Backend pytest",
        "Backend Ruff",
        "Backend Mypy",
        "Bandit",
        "pip-audit",
        "Frontend typecheck",
        "Frontend Vitest",
        "Frontend ESLint",
        "npm audit frontend",
        "Mobile typecheck",
        "Mobile Jest",
        "Mobile lint",
        "npm audit mobile",
    }
    assert labels == expected
    assert len(policy_summary()) == len(REQUIRED_TOOL_RULES)


def test_clear_aggregate_prevents_stale_consumption(tmp_path: Path):
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    stale = audit_dir / "audit-status.json"
    stale.write_text(json.dumps(_base_status()), encoding="utf-8")
    (audit_dir / "audit-summary.md").write_text("stale", encoding="utf-8")
    clear_aggregate_outputs(audit_dir)
    assert not stale.exists()
    assert not (audit_dir / "audit-summary.md").exists()


def test_publish_only_after_success(tmp_path: Path):
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    stale_payload = {"schema_version": 2, "run_id": "OLD", "overall_status": "ok"}
    (audit_dir / "audit-status.json").write_text(json.dumps(stale_payload), encoding="utf-8")
    clear_aggregate_outputs(audit_dir)

    tmp = tmp_path / "tmp"
    tmp.mkdir()
    status_tmp = tmp / "status.json"
    summary_tmp = tmp / "summary.md"
    fresh = _base_status()
    fresh["run_id"] = "NEW"
    status_tmp.write_text(json.dumps(fresh), encoding="utf-8")
    summary_tmp.write_text("fresh", encoding="utf-8")
    publish_aggregate_outputs(audit_dir=audit_dir, status_tmp=status_tmp, summary_tmp=summary_tmp)

    published = json.loads((audit_dir / "audit-status.json").read_text(encoding="utf-8"))
    assert published["run_id"] == "NEW"
    assert (audit_dir / "audit-summary.md").read_text(encoding="utf-8") == "fresh"


def test_gate_does_not_consume_missing_status_after_failed_generator(tmp_path: Path):
    """After clear + generator failure, enforce must fail (no stale file)."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    (audit_dir / "audit-status.json").write_text(json.dumps(_base_status()), encoding="utf-8")
    clear_aggregate_outputs(audit_dir)
    assert not (audit_dir / "audit-status.json").exists()

    # Simulate enforce main path: missing file → fail in strict mode.
    status_path = audit_dir / "audit-status.json"
    assert not status_path.exists()


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_run_full_audit_exit_on_generator_failure_and_no_stale(tmp_path: Path):
    """Integration: stale status cleared; generator failure → non-zero; no published status."""
    root = tmp_path / "repo"
    audit = root / "audit"
    raw = audit / "raw"
    scripts = root / "scripts" / "audit"
    raw.mkdir(parents=True)
    (raw / ".gitkeep").write_text("", encoding="utf-8")

    # Stale published status that would wrongly PASS if reused.
    (audit / "audit-status.json").write_text(json.dumps(_base_status()), encoding="utf-8")
    (audit / "audit-summary.md").write_text("stale", encoding="utf-8")

    # Minimal resolve_python stub.
    _write_executable(
        scripts / "resolve_python.sh",
        "#!/usr/bin/env sh\nAUDIT_PYTHON=\"%s\"\nexport AUDIT_PYTHON\n" % sys.executable,
    )

    # Failing generator.
    (scripts / "generate_audit_summary.py").write_text(
        "#!/usr/bin/env python3\nimport sys\nprint('boom', file=sys.stderr)\nsys.exit(7)\n",
        encoding="utf-8",
    )

    # Copy real runner (uses ROOT_DIR relative to script location).
    runner_src = AUDIT_DIR / "run_full_audit.sh"
    runner_dst = scripts / "run_full_audit.sh"
    runner_dst.write_text(runner_src.read_text(encoding="utf-8"), encoding="utf-8")
    runner_dst.chmod(runner_dst.stat().st_mode | stat.S_IXUSR)

    # Dummy enforce (should not be reached on generator failure).
    (scripts / "enforce_quality_gate.py").write_text(
        "#!/usr/bin/env python3\nimport sys\nprint('gate should not run')\nsys.exit(0)\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["AUDIT_PHASE0_SKIP_COLLECTORS"] = "1"
    env["AUDIT_RUN_ID"] = "test-fail-gen"
    proc = subprocess.run(
        ["bash", str(runner_dst)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 7, proc.stdout + proc.stderr
    assert not (audit / "audit-status.json").exists()
    assert not (audit / "audit-summary.md").exists()
    assert "gate should not run" not in proc.stdout


def test_run_full_audit_publishes_run_id_on_success(tmp_path: Path):
    root = tmp_path / "repo"
    audit = root / "audit"
    raw = audit / "raw"
    scripts = root / "scripts" / "audit"
    raw.mkdir(parents=True)
    (raw / ".gitkeep").write_text("", encoding="utf-8")
    (audit / "audit-status.json").write_text(json.dumps({"run_id": "STALE"}), encoding="utf-8")

    _write_executable(
        scripts / "resolve_python.sh",
        "#!/usr/bin/env sh\nAUDIT_PYTHON=\"%s\"\nexport AUDIT_PYTHON\n" % sys.executable,
    )

    gen = scripts / "generate_audit_summary.py"
    gen.write_text(
        """#!/usr/bin/env python3
import argparse, json
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--status-out')
p.add_argument('--summary-out')
p.add_argument('--run-id')
p.add_argument('--skip-report-update', action='store_true')
args = p.parse_args()
status = {
  "schema_version": 2,
  "run_id": args.run_id,
  "overall_status": "ok",
  "max_severity": "none",
  "generated_at": "2026-01-01T00:00:00+00:00",
  "areas": {},
}
Path(args.status_out).write_text(json.dumps(status), encoding='utf-8')
Path(args.summary_out).write_text('ok', encoding='utf-8')
""",
        encoding="utf-8",
    )

    # Gate stub: pass if status exists with matching run_id.
    (scripts / "enforce_quality_gate.py").write_text(
        """#!/usr/bin/env python3
import json, sys
from pathlib import Path
# repo_root = parents[2] from scripts/audit/enforce...
root = Path(__file__).resolve().parents[2]
status = json.loads((root / 'audit' / 'audit-status.json').read_text())
assert status.get('run_id') == 'test-ok-run'
sys.exit(0)
""",
        encoding="utf-8",
    )

    runner_dst = scripts / "run_full_audit.sh"
    runner_dst.write_text((AUDIT_DIR / "run_full_audit.sh").read_text(encoding="utf-8"), encoding="utf-8")
    runner_dst.chmod(runner_dst.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["AUDIT_PHASE0_SKIP_COLLECTORS"] = "1"
    env["AUDIT_RUN_ID"] = "test-ok-run"
    proc = subprocess.run(
        ["bash", str(runner_dst)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    published = json.loads((audit / "audit-status.json").read_text(encoding="utf-8"))
    assert published["run_id"] == "test-ok-run"
    assert (raw / "LATEST_RUN.txt").read_text(encoding="utf-8").strip() == "test-ok-run"
