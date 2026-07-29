"""CLI: reconcile aisle diagnostics (dry-run by default).

Usage:
  python -m scripts.ops.reconcile_aisle --aisle-id <id> --dry-run --actor ops --reason 'check'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile aisle operational state (dry-run default)")
    parser.add_argument("--aisle-id", required=True)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    dry_run = not args.confirm
    from src.observability.job_state_consistency import audit_job_row
    from src.observability.logging import log_event
    from src.runtime.app_container import get_app_container

    container = get_app_container()
    aisle = container.get_aisle_repository().get_by_id(args.aisle_id)
    if aisle is None:
        print(json.dumps({"ok": False, "error": "aisle_not_found", "aisle_id": args.aisle_id}))
        return 1

    job = None
    op_job_id = getattr(aisle, "operational_job_id", None)
    if op_job_id:
        job = container.get_job_repository().get_by_id(op_job_id)
    findings = audit_job_row(job, aisle=aisle) if job is not None else []
    if job is None and getattr(aisle, "status", None) is not None:
        findings = []

    payload = {
        "ok": True,
        "dry_run": dry_run,
        "aisle_id": args.aisle_id,
        "aisle_status": getattr(getattr(aisle, "status", None), "value", getattr(aisle, "status", None)),
        "operational_job_id": op_job_id,
        "actor": args.actor,
        "reason": args.reason,
        "findings": [{"kind": f.kind.value, "action": f.action.value, "detail": f.detail} for f in findings],
        "action": "diagnose_only" if dry_run else "manual_admin_required",
    }
    log_event(
        "aisle_reconcile_inspected",
        component="ops",
        operation="reconcile_aisle",
        outcome="dry_run" if dry_run else "manual",
        aisle_id=args.aisle_id,
        actor=args.actor,
        reason_code=args.reason,
    )
    if not dry_run:
        payload["ok"] = False
        payload["error"] = "mutating_reconcile_via_cli_not_enabled_use_admin_apis"
        print(json.dumps(payload, indent=2, default=str))
        return 2
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
