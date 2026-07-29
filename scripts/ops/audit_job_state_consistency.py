"""CLI: audit job/aisle consistency (dry-run by default).

Usage:
  python -m scripts.ops.audit_job_state_consistency --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without install.
_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit job/aisle operational consistency")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Read-only (default)")
    parser.add_argument("--apply", action="store_true", help="Reserved; mutations not implemented")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings")
    parser.add_argument("--limit", type=int, default=200, help="Max jobs to scan")
    args = parser.parse_args(argv)

    if args.apply:
        print("ERROR: --apply is not implemented; use admin recovery tools with dry-run.", file=sys.stderr)
        return 2

    from src.observability.job_state_consistency import audit_jobs
    from src.runtime.app_container import get_app_container

    container = get_app_container()
    job_repo = container.get_job_repository()
    aisle_repo = container.get_aisle_repository()

    # Prefer list helpers if present; otherwise empty scan with clear message.
    jobs = []
    if hasattr(job_repo, "list_recent"):
        jobs = list(job_repo.list_recent(limit=args.limit))
    elif hasattr(job_repo, "list_all"):
        jobs = list(job_repo.list_all())[: args.limit]
    else:
        print(
            "WARN: job repository has no list_recent/list_all; "
            "pass jobs via unit tests or extend repository for ops scan.",
            file=sys.stderr,
        )

    aisle_by_id: dict = {}
    for job in jobs:
        if getattr(job, "target_type", None) == "aisle":
            aid = getattr(job, "target_id", None)
            if aid and aid not in aisle_by_id:
                aisle = aisle_repo.get_by_id(aid) if hasattr(aisle_repo, "get_by_id") else None
                if aisle is not None:
                    aisle_by_id[aid] = aisle

    findings = audit_jobs(jobs, aisle_by_id=aisle_by_id)
    if args.json:
        payload = [
            {
                "kind": f.kind.value,
                "action": f.action.value,
                "job_id": f.job_id,
                "aisle_id": f.aisle_id,
                "detail": f.detail,
            }
            for f in findings
        ]
        print(json.dumps({"dry_run": True, "count": len(payload), "findings": payload}, indent=2))
    else:
        print(f"dry_run=true jobs_scanned={len(jobs)} findings={len(findings)}")
        for f in findings:
            print(f"- {f.kind.value} action={f.action.value} job_id={f.job_id} aisle_id={f.aisle_id} {f.detail}")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
