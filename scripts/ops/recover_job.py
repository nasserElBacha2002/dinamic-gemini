"""CLI: recover job (dry-run by default; mutate requires --confirm).

Usage:
  python -m scripts.ops.recover_job --job-id <id> --dry-run --actor ops --reason 'stale'
  python -m scripts.ops.recover_job --job-id <id> --confirm --actor ops --reason 'stale'
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logger = logging.getLogger("dinamic.ops.recover_job")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recover a stale/failed job (ops)")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--confirm", action="store_true", help="Execute mutation (disables dry-run)")
    parser.add_argument("--actor", required=True, help="Operator identity for audit")
    parser.add_argument("--reason", required=True, help="Mandatory reason")
    args = parser.parse_args(argv)

    dry_run = not args.confirm
    from src.config import load_settings
    from src.observability.job_state_consistency import audit_job_row
    from src.observability.logging import log_event
    from src.runtime.app_container import get_app_container

    container = get_app_container()
    job_repo = container.get_job_repository()
    job = job_repo.get_by_id(args.job_id)
    if job is None:
        print(json.dumps({"ok": False, "error": "job_not_found", "job_id": args.job_id}))
        return 1

    aisle = None
    if getattr(job, "target_type", None) == "aisle":
        aisle = container.get_aisle_repository().get_by_id(job.target_id)

    findings = audit_job_row(job, aisle=aisle)
    status = getattr(getattr(job, "status", None), "value", getattr(job, "status", None))
    lease_expires = getattr(job, "lease_expires_at", None)
    has_active_lease = False
    if status in {"RUNNING", "STARTING", "CANCEL_REQUESTED"} and lease_expires is not None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        exp = lease_expires if lease_expires.tzinfo else lease_expires.replace(tzinfo=timezone.utc)
        if exp >= now and getattr(job, "claim_owner_id", None):
            has_active_lease = True

    result = {
        "ok": True,
        "dry_run": dry_run,
        "job_id": job.id,
        "status": status,
        "actor": args.actor,
        "reason": args.reason,
        "has_active_lease": has_active_lease,
        "findings": [{"kind": f.kind.value, "action": f.action.value} for f in findings],
        "action": "none",
    }

    if has_active_lease:
        result["ok"] = False
        result["error"] = "active_lease_present"
        result["action"] = "refused"
        log_event(
            "job_recovery_refused",
            component="ops",
            operation="recover_job",
            outcome="refused",
            reason_code="ACTIVE_LEASE",
            job_id=job.id,
            actor=args.actor,
        )
        print(json.dumps(result, indent=2, default=str))
        return 3

    if dry_run:
        result["action"] = "would_stale_fail_or_manual_admin"
        log_event(
            "job_recovery_started",
            component="ops",
            operation="recover_job",
            outcome="dry_run",
            job_id=job.id,
            actor=args.actor,
            reason_code=args.reason,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0

    # Mutating path: only stale reclaim CAS if repository supports it.
    if not hasattr(job_repo, "try_reclaim_stale_job_and_reconcile_aisle"):
        result["ok"] = False
        result["error"] = "reclaim_unsupported"
        print(json.dumps(result, indent=2, default=str))
        return 4

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    settings = load_settings()
    stale_after = int(getattr(settings, "worker_stale_running_timeout_sec", 900) or 900)
    reclaim = job_repo.try_reclaim_stale_job_and_reconcile_aisle(
        job.id, now=now, stale_after_seconds=stale_after
    )
    result["action"] = "stale_fail_reclaim"
    result["won"] = bool(getattr(reclaim, "won", False))
    result["after_status"] = getattr(
        getattr(getattr(reclaim, "job", None), "status", None),
        "value",
        None,
    )
    log_event(
        "job_recovery_completed" if result["won"] else "job_recovery_failed",
        component="ops",
        operation="recover_job",
        outcome="ok" if result["won"] else "lost_cas",
        job_id=job.id,
        actor=args.actor,
        reason_code=args.reason,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["won"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
