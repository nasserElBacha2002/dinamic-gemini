#!/usr/bin/env python3
"""Quality Gate enforcement (Phase 0) — consumes structured audit-status.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_AUDIT_DIR = Path(__file__).resolve().parent
if str(_AUDIT_DIR) not in sys.path:
    sys.path.insert(0, str(_AUDIT_DIR))

from lib.gate_policy import REQUIRED_AREAS, REQUIRED_TOOL_RULES, ToolGateRule  # noqa: E402
from lib.git_provenance import current_git_sha, working_tree_status  # noqa: E402
from lib.schema import SchemaValidationError, normalize_status_document  # noqa: E402
from lib.statuses import (  # noqa: E402
    ToolStatus,
    is_invalidating,
    is_omitted,
    normalize_legacy_status,
)


def _get_nested(data: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _tool(status: Dict[str, Any], area: str, tool: str) -> Dict[str, Any]:
    tools = _get_nested(status, ["areas", area, "tools"], {}) or {}
    return tools.get(tool, {}) if isinstance(tools, dict) else {}


def _evaluate_required_tool(
    *,
    rule: ToolGateRule,
    tool: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    label = rule.label
    reasons: List[str] = []
    checks: List[str] = []
    if not tool:
        reasons.append(f"{label}: tool entry missing from audit-status.json")
        checks.append(f"- {label}: FAIL (missing)")
        return reasons, checks

    st = normalize_legacy_status(str(tool.get("status", ToolStatus.NOT_RUN.value)))
    metrics = tool.get("metrics") or {}
    failed = 0
    for key in rule.failed_metric_keys:
        failed += _int_or_zero(metrics.get(key))

    if is_invalidating(st):
        err = tool.get("error") or tool.get("observation") or st
        reasons.append(f"{label}: tooling invalid ({st}) — {err}")
        checks.append(f"- {label}: FAIL ({st})")
        return reasons, checks

    if is_omitted(st) or st == ToolStatus.NOT_AVAILABLE.value:
        reasons.append(f"{label}: not executed ({st}) — required for gate")
        checks.append(f"- {label}: FAIL ({st})")
        return reasons, checks

    if failed > 0:
        reasons.append(f"{label}: failing count={failed}")
        checks.append(f"- {label}: FAIL ({failed})")
        return reasons, checks

    if st == ToolStatus.FINDINGS.value and not rule.allow_findings:
        reasons.append(f"{label}: FINDINGS")
        checks.append(f"- {label}: FAIL (FINDINGS)")
        return reasons, checks

    note = " (findings allowed)" if st == ToolStatus.FINDINGS.value and rule.allow_findings else ""
    checks.append(f"- {label}: OK ({st}){note}")
    return reasons, checks


def evaluate_gate(status: Dict[str, Any], *, repo_root: Path | None = None) -> Tuple[bool, List[str], List[str]]:
    reasons: List[str] = []
    checks: List[str] = []

    try:
        status, schema_notes = normalize_status_document(status)
        for note in schema_notes:
            checks.append(f"- schema: {note}")
    except SchemaValidationError as exc:
        reasons.append(f"schema validation: {exc}")
        checks.append(f"- schema: FAIL ({exc})")
        return False, reasons, checks

    schema = status.get("schema_version")
    checks.append(f"- schema_version: {schema}")

    run_id = status.get("run_id")
    if run_id:
        checks.append(f"- run_id: {run_id}")
    generated_at = status.get("generated_at")
    if generated_at:
        checks.append(f"- generated_at: {generated_at}")

    if repo_root is not None:
        recorded_sha = status.get("git_sha")
        head_sha = current_git_sha(repo_root)
        if recorded_sha and head_sha and recorded_sha != head_sha:
            reasons.append(
                f"audit git_sha mismatch: status={recorded_sha} current HEAD={head_sha}"
            )
            checks.append("- git_sha: FAIL (stale snapshot)")
        elif recorded_sha and head_sha:
            checks.append(f"- git_sha: OK ({recorded_sha})")
        elif not recorded_sha:
            reasons.append("audit git_sha missing — cannot prove snapshot matches current HEAD")
            checks.append("- git_sha: FAIL (missing)")
        else:
            checks.append("- git_sha: WARN (HEAD unavailable)")

        recorded_tree = str(status.get("working_tree_status") or "").lower()
        current_tree = working_tree_status(repo_root)
        if recorded_tree == "clean" and current_tree == "dirty":
            reasons.append(
                "working tree is dirty but audit was recorded on a clean tree"
            )
            checks.append("- working_tree_status: FAIL (dirty vs audited clean)")
        elif recorded_tree in {"clean", "dirty"}:
            checks.append(f"- working_tree_status: OK (recorded={recorded_tree}, current={current_tree})")
        elif recorded_tree:
            checks.append(f"- working_tree_status: recorded={recorded_tree}, current={current_tree}")
        else:
            checks.append("- working_tree_status: not recorded")

        started_at = status.get("started_at")
        finished_at = status.get("finished_at")
        if started_at:
            checks.append(f"- started_at: {started_at}")
        if finished_at:
            checks.append(f"- finished_at: {finished_at}")

    for area in sorted(REQUIRED_AREAS):
        if _get_nested(status, ["areas", area]) is None:
            reasons.append(f"Required area missing: {area}")
            checks.append(f"- {area} area: FAIL (missing)")

    for rule in REQUIRED_TOOL_RULES:
        if not rule.required:
            continue
        r, c = _evaluate_required_tool(rule=rule, tool=_tool(status, rule.area, rule.tool))
        reasons.extend(r)
        checks.extend(c)

    # Structured security exceptions (must exist, valid schema, not expired).
    try:
        from lib.security_exceptions import (
            SecurityExceptionsError,
            default_exceptions_path,
            load_security_exceptions,
            validate_security_exceptions_not_expired,
        )

        exc_path = default_exceptions_path(Path(__file__).resolve().parents[2])
        exceptions = load_security_exceptions(exc_path)
        validate_security_exceptions_not_expired(exceptions)
        checks.append(f"- security-exceptions: OK ({len(exceptions)} entries, not expired)")
    except SecurityExceptionsError as exc:
        reasons.append(f"security-exceptions: {exc}")
        checks.append(f"- security-exceptions: FAIL ({exc})")
    except OSError as exc:
        reasons.append(f"security-exceptions: {exc}")
        checks.append(f"- security-exceptions: FAIL ({exc})")

    max_severity = str(status.get("max_severity", "none")).lower()
    overall_status = str(status.get("overall_status", "ok")).lower()
    checks.append(f"- Max severity: {max_severity}")
    checks.append(f"- Overall status: {overall_status}")

    if max_severity == "critical":
        reasons.append("Max severity: critical")
    if overall_status == "error":
        reasons.append("Overall status: error (tooling/parse invalidating)")

    seen = set()
    uniq_reasons: List[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            uniq_reasons.append(reason)

    passed = len(uniq_reasons) == 0
    return passed, uniq_reasons, checks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evalúa política del Quality Gate (Phase 0 structured statuses)."
    )
    parser.add_argument(
        "--status-file",
        default="audit/audit-status.json",
        help="Ruta al JSON consolidado de auditoría (default: audit/audit-status.json).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Si está activo, devuelve exit 1 cuando el gate falla.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    status_path = (repo_root / args.status_file).resolve()

    if not status_path.exists():
        print("Quality Gate Result: FAIL")
        print("")
        print("Reasons:")
        print(f"- audit-status.json no encontrado: {status_path}")
        print("  (no se usa evidencia de corridas anteriores)")
        print("")
        print("Deploy blocked")
        return 1 if args.strict else 0

    try:
        status_data = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print("Quality Gate Result: FAIL")
        print("")
        print("Reasons:")
        print(f"- Error leyendo/parsing audit-status.json: {exc}")
        print("")
        print("Deploy blocked")
        return 1 if args.strict else 0

    passed, reasons, checks = evaluate_gate(status_data, repo_root=repo_root)

    print(f"Quality Gate Result: {'PASS' if passed else 'FAIL'}")
    print("")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print("Checks:")
    for line in checks:
        print(line)
    print("")

    if passed:
        print("Deploy allowed")
    else:
        print("Reasons:")
        for reason in reasons:
            print(f"- {reason}")
        print("")
        print("Deploy blocked")

    if args.strict:
        return 0 if passed else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
