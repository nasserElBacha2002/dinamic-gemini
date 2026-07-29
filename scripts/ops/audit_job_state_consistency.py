"""CLI: audit job/aisle consistency (dry-run by default).

Usage:
  python -m scripts.ops.audit_job_state_consistency --dry-run
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
    parser = argparse.ArgumentParser(description="Audit job/aisle operational consistency")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Read-only (default)")
    mode.add_argument("--confirm", action="store_true", help="Reserved; mutations not implemented")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings")
    parser.add_argument("--limit", type=int, default=200, help="Max jobs to scan")
    args = parser.parse_args(argv)

    if args.confirm:
        print(
            "ERROR: --confirm is not implemented for consistency audit; use admin recovery tools.",
            file=sys.stderr,
        )
        return 2

    from src.application.ports.repositories import JobRepository
    from src.observability.job_state_consistency import audit_jobs
    from src.runtime.app_container import get_app_container

    container = get_app_container()
    job_repo = container.get_job_repository()
    aisle_repo = container.get_aisle_repository()

    if not isinstance(job_repo, JobRepository):
        print("ERROR: job repository port unavailable", file=sys.stderr)
        return 4

    try:
        jobs = list(job_repo.list_jobs_for_ops_scan(limit=args.limit))
    except NotImplementedError as exc:
        print(f"ERROR: ops scan unsupported: {exc}", file=sys.stderr)
        return 4

    aisle_ids = {
        j.target_id
        for j in jobs
        if j.target_type == "aisle" and isinstance(j.target_id, str) and j.target_id
    }
    aisle_by_id = {}
    for aid in aisle_ids:
        aisle = aisle_repo.get_by_id(aid)
        if aisle is not None:
            aisle_by_id[aid] = aisle

    findings = audit_jobs(jobs, aisle_by_id=aisle_by_id)
    payload = {
        "dry_run": True,
        "jobs_scanned": len(jobs),
        "findings_count": len(findings),
        "scan_backend": type(job_repo).__name__,
        "findings": [
            {
                "kind": f.kind.value,
                "action": f.action.value,
                "job_id": f.job_id,
                "aisle_id": f.aisle_id,
                "detail": f.detail,
            }
            for f in findings
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"dry_run=true jobs_scanned={payload['jobs_scanned']} "
            f"findings={payload['findings_count']} backend={payload['scan_backend']}"
        )
        for f in findings:
            print(
                f"- {f.kind.value} action={f.action.value} "
                f"job_id={f.job_id} aisle_id={f.aisle_id} {f.detail}"
            )
    # Empty DB is success (0 findings); unsupported scan already failed above.
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
