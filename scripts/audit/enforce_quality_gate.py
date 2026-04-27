#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


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


def evaluate_gate(status: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    reasons: List[str] = []
    checks: List[str] = []

    backend_failed = _int_or_zero(
        _get_nested(status, ["areas", "backend", "highlights", "pytest_failed"], None)
    )
    if backend_failed == 0:
        backend_failed = _int_or_zero(
            _get_nested(status, ["areas", "backend", "tools", "pytest", "metrics", "failed"], 0)
        )

    frontend_failed = _int_or_zero(
        _get_nested(status, ["areas", "frontend", "highlights", "vitest_failed_tests"], None)
    )
    if frontend_failed == 0:
        frontend_failed = _int_or_zero(
            _get_nested(status, ["areas", "frontend", "tools", "vitest", "metrics", "failed_tests"], 0)
        )

    max_severity = str(status.get("max_severity", "none")).lower()
    overall_status = str(status.get("overall_status", "ok")).lower()

    if backend_failed > 0:
        reasons.append(f"Backend tests failing: {backend_failed}")
        checks.append(f"- Backend tests: FAIL ({backend_failed})")
    else:
        checks.append("- Backend tests: OK")

    if frontend_failed > 0:
        reasons.append(f"Frontend tests failing: {frontend_failed}")
        checks.append(f"- Frontend tests: FAIL ({frontend_failed})")
    else:
        checks.append("- Frontend tests: OK")

    checks.append(f"- Max severity: {max_severity}")
    checks.append(f"- Overall status: {overall_status}")

    if max_severity == "critical":
        reasons.append("Max severity: critical")
    if overall_status == "error":
        reasons.append("Overall status: error")

    passed = len(reasons) == 0
    return passed, reasons, checks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evalúa política progresiva del Quality Gate (Fase 5)."
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
