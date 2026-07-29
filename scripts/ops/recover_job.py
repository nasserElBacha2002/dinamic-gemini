"""CLI: recover job via RecoverStaleJobUseCase (dry-run by default).

Usage:
  python -m scripts.ops.recover_job --job-id <id> --dry-run --actor ops --reason 'stale'
  python -m scripts.ops.recover_job --job-id <id> --confirm --actor ops --reason 'stale'
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
    parser = argparse.ArgumentParser(description="Recover a stale job (ops)")
    parser.add_argument("--job-id", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm", action="store_true")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    from src.application.services.aisle_job_launch_service import AisleJobLaunchService
    from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
    from src.application.use_cases.recovery.recover_stale_job import (
        RecoverStaleJobCommand,
        RecoverStaleJobOutcome,
        RecoverStaleJobUseCase,
    )
    from src.config import load_settings
    from src.infrastructure.adapters.clock import UtcClock
    from src.runtime.app_container import get_app_container

    container = get_app_container()
    settings = load_settings()
    job_repo = container.get_job_repository()
    aisle_repo = container.get_aisle_repository()
    clock = UtcClock()
    launch = AisleJobLaunchService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        worker_launch_service=container.get_worker_launch_service(),
        clock=clock,
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=container.get_inventory_repository(),
            aisle_repo=aisle_repo,
            clock=clock,
        ),
    )
    uc = RecoverStaleJobUseCase(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        launch_service=launch,
        clock=clock,
    )
    result = uc.execute(
        RecoverStaleJobCommand(
            job_id=args.job_id,
            actor=args.actor,
            reason=args.reason,
            dry_run=bool(args.dry_run),
            stale_after_seconds=int(settings.worker_stale_running_timeout_sec or 900),
            max_attempts=int(settings.recovery_max_attempts or 3),
        )
    )
    print(
        json.dumps(
            {
                "outcome": result.outcome.value,
                "job_id": result.job_id,
                "new_job_id": result.new_job_id,
                "detail": result.detail,
                "dry_run": bool(args.dry_run),
                "actor": args.actor,
                "reason": args.reason,
            },
            indent=2,
        )
    )
    if result.outcome in {
        RecoverStaleJobOutcome.RECOVERED,
        RecoverStaleJobOutcome.RELAUNCHED,
        RecoverStaleJobOutcome.DRY_RUN,
        RecoverStaleJobOutcome.ALREADY_RECOVERED,
    }:
        return 0
    if result.outcome == RecoverStaleJobOutcome.CHILD_TERMINAL:
        return 4
    if result.outcome == RecoverStaleJobOutcome.ACTIVE_LEASE:
        return 3
    if result.outcome == RecoverStaleJobOutcome.LOST_CAS:
        return 5
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
