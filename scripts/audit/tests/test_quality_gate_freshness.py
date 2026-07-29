"""Quality gate freshness — stale snapshot, dirty tree, unavailable scanner."""

from __future__ import annotations

import sys
from pathlib import Path

AUDIT_DIR = Path(__file__).resolve().parents[1]
if str(AUDIT_DIR) not in sys.path:
    sys.path.insert(0, str(AUDIT_DIR))

from enforce_quality_gate import evaluate_gate  # noqa: E402
from lib.git_provenance import current_git_sha  # noqa: E402


def _base_status(*, git_sha: str | None = "abc123", tree: str = "clean") -> dict:
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
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:05+00:00",
        "git_sha": git_sha,
        "working_tree_status": tree,
        "areas": {
            "backend": {
                "status": "OK",
                "tools": {
                    "pytest": ok_tool({"passed": 10, "failed": 0}),
                    "ruff": ok_tool({"issues": 0}),
                    "mypy": ok_tool({"errors": 0}),
                    "bandit": ok_tool({"high": 0, "blocking_high": 0}),
                    "pip-audit": ok_tool({"total": 0}),
                    "gitleaks": ok_tool({"secrets": 0}),
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


def test_gate_fails_on_stale_git_sha() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    head = current_git_sha(repo_root)
    status = _base_status(git_sha="deadbeef00000000000000000000000000000000")
    passed, reasons, _ = evaluate_gate(status, repo_root=repo_root)
    assert passed is False
    if head:
        assert any("git_sha mismatch" in r for r in reasons)
    else:
        assert any("git_sha missing" in r for r in reasons)


def test_gate_fails_when_tree_dirty_after_clean_audit(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    head = current_git_sha(repo_root)
    status = _base_status(git_sha=head, tree="clean")
    (repo_root / "freshness_probe_marker").write_text("dirty-me", encoding="utf-8")
    try:
        passed, reasons, _ = evaluate_gate(status, repo_root=repo_root)
        assert passed is False
        assert any("dirty but audit was recorded on a clean tree" in r for r in reasons)
    finally:
        probe = repo_root / "freshness_probe_marker"
        if probe.exists():
            probe.unlink()


def test_gate_fails_on_gitleaks_not_available() -> None:
    status = _base_status()
    status["areas"]["backend"]["tools"]["gitleaks"] = {
        "status": "NOT_AVAILABLE",
        "severity": "info",
        "metrics": {},
        "report": "x",
        "observation": "binary missing",
        "exit_code": 127,
        "error": None,
    }
    passed, reasons, _ = evaluate_gate(status)
    assert passed is False
    assert any("Gitleaks" in r and "NOT_AVAILABLE" in r for r in reasons)
