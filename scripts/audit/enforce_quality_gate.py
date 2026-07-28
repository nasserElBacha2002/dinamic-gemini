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
    label: str,
    tool: Dict[str, Any],
    failed_metric_keys: Tuple[str, ...],
    allow_findings: bool = False,
) -> Tuple[List[str], List[str]]:
    reasons: List[str] = []
    checks: List[str] = []
    if not tool:
        reasons.append(f"{label}: tool entry missing from audit-status.json")
        checks.append(f"- {label}: FAIL (missing)")
        return reasons, checks

    st = normalize_legacy_status(str(tool.get("status", ToolStatus.NOT_RUN.value)))
    metrics = tool.get("metrics") or {}
    failed = 0
    for key in failed_metric_keys:
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

    if st == ToolStatus.FINDINGS.value and not allow_findings:
        # Findings without failed tests (e.g. type errors) still block when required.
        reasons.append(f"{label}: FINDINGS")
        checks.append(f"- {label}: FAIL (FINDINGS)")
        return reasons, checks

    checks.append(f"- {label}: OK ({st})")
    return reasons, checks


def evaluate_gate(status: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    reasons: List[str] = []
    checks: List[str] = []

    schema = status.get("schema_version")
    checks.append(f"- schema_version: {schema if schema is not None else 'missing (legacy)'}")

    # Backend pytest (required)
    r, c = _evaluate_required_tool(
        label="Backend pytest",
        tool=_tool(status, "backend", "pytest"),
        failed_metric_keys=("failed", "errors"),
    )
    reasons.extend(r)
    checks.extend(c)

    # Backend ruff / mypy — findings block in strict gate
    for tool_key, label in (("ruff", "Backend ruff"), ("mypy", "Backend mypy")):
        r, c = _evaluate_required_tool(
            label=label,
            tool=_tool(status, "backend", tool_key),
            failed_metric_keys=("issues", "errors"),
        )
        reasons.extend(r)
        checks.extend(c)

    # Frontend vitest + typecheck
    r, c = _evaluate_required_tool(
        label="Frontend vitest",
        tool=_tool(status, "frontend", "vitest"),
        failed_metric_keys=("failed_tests",),
    )
    reasons.extend(r)
    checks.extend(c)

    r, c = _evaluate_required_tool(
        label="Frontend typecheck",
        tool=_tool(status, "frontend", "typecheck"),
        failed_metric_keys=("ts_errors",),
    )
    reasons.extend(r)
    checks.extend(c)

    # Mobile (required Phase 0)
    mobile_area = _get_nested(status, ["areas", "mobile"])
    if mobile_area is None:
        reasons.append("Mobile area missing from audit-status.json")
        checks.append("- Mobile area: FAIL (missing)")
    else:
        r, c = _evaluate_required_tool(
            label="Mobile jest",
            tool=_tool(status, "mobile", "jest"),
            failed_metric_keys=("failed",),
        )
        reasons.extend(r)
        checks.extend(c)
        r, c = _evaluate_required_tool(
            label="Mobile typecheck",
            tool=_tool(status, "mobile", "typecheck"),
            failed_metric_keys=("ts_errors",),
        )
        reasons.extend(r)
        checks.extend(c)

    max_severity = str(status.get("max_severity", "none")).lower()
    overall_status = str(status.get("overall_status", "ok")).lower()
    checks.append(f"- Max severity: {max_severity}")
    checks.append(f"- Overall status: {overall_status}")

    if max_severity == "critical":
        # Only block on critical if it comes from executed findings, not parse noise.
        # Still report — pytest/jest failures already set critical.
        reasons.append("Max severity: critical")
    if overall_status == "error":
        reasons.append("Overall status: error (tooling/parse invalidating)")

    # Deduplicate reasons while preserving order
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

    passed, reasons, checks = evaluate_gate(status_data)

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
