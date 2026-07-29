"""CLI: inspect aisle operational state (read-only; no mutations).

Usage:
  python -m scripts.ops.inspect_aisle --aisle-id <id> --dry-run --actor ops --reason 'check'
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
    parser = argparse.ArgumentParser(description="Inspect aisle operational state (read-only)")
    parser.add_argument("--aisle-id", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Read-only inspection (required)")
    mode.add_argument(
        "--confirm",
        action="store_true",
        help="Reserved; mutating reconcile is not enabled via this CLI",
    )
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    if args.confirm:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "mutating_reconcile_via_cli_not_enabled_use_admin_apis",
                    "aisle_id": args.aisle_id,
                },
                indent=2,
            )
        )
        return 2

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

    payload = {
        "ok": True,
        "dry_run": True,
        "aisle_id": args.aisle_id,
        "aisle_status": getattr(getattr(aisle, "status", None), "value", getattr(aisle, "status", None)),
        "operational_job_id": op_job_id,
        "actor": args.actor,
        "reason": args.reason,
        "findings": [
            {"kind": f.kind.value, "action": f.action.value, "detail": f.detail} for f in findings
        ],
        "action": "diagnose_only",
    }
    log_event(
        "aisle_inspect_completed",
        component="ops",
        operation="inspect_aisle",
        outcome="ok",
        aisle_id=args.aisle_id,
        actor=args.actor,
        reason_code=args.reason,
    )
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
