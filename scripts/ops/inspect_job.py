"""CLI: inspect a job for operators (read-only).

Usage:
  python -m scripts.ops.inspect_job --job-id <id>
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
    parser = argparse.ArgumentParser(description="Inspect a job (no secrets)")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from src.observability.job_state_consistency import audit_job_row
    from src.pipeline.secret_redaction import redact_secrets_in_text
    from src.runtime.app_container import get_app_container

    container = get_app_container()
    job = container.get_job_repository().get_by_id(args.job_id)
    if job is None:
        print(f"job not found: {args.job_id}", file=sys.stderr)
        return 1

    aisle = None
    if getattr(job, "target_type", None) == "aisle":
        aisle = container.get_aisle_repository().get_by_id(job.target_id)

    findings = audit_job_row(job, aisle=aisle)
    payload = {
        "job_id": job.id,
        "status": getattr(getattr(job, "status", None), "value", getattr(job, "status", None)),
        "execution_id": getattr(job, "execution_id", None),
        "claim_owner_id": getattr(job, "claim_owner_id", None),
        "lease_expires_at": str(getattr(job, "lease_expires_at", None)),
        "failure_code": getattr(job, "failure_code", None),
        "finished_at": str(getattr(job, "finished_at", None)),
        "aisle_id": getattr(aisle, "id", None) if aisle else None,
        "aisle_status": (
            getattr(getattr(aisle, "status", None), "value", getattr(aisle, "status", None))
            if aisle
            else None
        ),
        "findings": [
            {"kind": f.kind.value, "action": f.action.value, "detail": f.detail} for f in findings
        ],
    }
    text = json.dumps(payload, indent=2, default=str)
    print(redact_secrets_in_text(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
