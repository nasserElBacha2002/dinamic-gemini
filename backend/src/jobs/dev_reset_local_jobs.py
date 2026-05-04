"""Dev utility: reset local non-terminal jobs to avoid stale test contamination.

Usage:
  python -m src.jobs.dev_reset_local_jobs --apply --purge-output
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Iterable
from pathlib import Path

from src.config import load_settings

NON_TERMINAL = ("queued", "running", "cancel_requested")


def _iter_local_non_terminal_job_dirs(output_dir: Path) -> Iterable[str]:
    if not output_dir.exists():
        return []
    job_ids: list[str] = []
    for child in output_dir.iterdir():
        if not child.is_dir():
            continue
        job_file = child / "job.json"
        if not job_file.exists():
            continue
        try:
            data = json.loads(job_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        status = str(data.get("status") or "").strip().lower()
        if status in NON_TERMINAL:
            job_ids.append(child.name)
    return job_ids


def _reset_sql_jobs(apply: bool) -> tuple[int, list[str]]:
    settings = load_settings()
    if not settings.sqlserver_enabled or not settings.sqlserver_effective_connection_string:
        return 0, []
    from src.database.sqlserver import SqlServerClient

    try:
        client = SqlServerClient(settings.require_sqlserver_connection_string())
        ids: list[str] = []
        with client.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM inventory_jobs
                WHERE status IN ('queued', 'running', 'cancel_requested')
                """
            )
            ids = [
                str(getattr(r, "id", "")) for r in (cur.fetchall() or []) if getattr(r, "id", None)
            ]
            if apply and ids:
                cur.execute(
                    """
                    UPDATE inventory_jobs
                    SET status = 'failed',
                        error_message = 'Local dev reset: non-terminal job reset',
                        updated_at = GETUTCDATE()
                    WHERE status IN ('queued', 'running', 'cancel_requested')
                    """
                )
        return len(ids), ids
    except Exception as e:
        print(f"[dev-reset] SQL unavailable, skipping DB reset: {e}")
        return 0, []


def _purge_output_dirs(output_dir: Path, job_ids: Iterable[str], apply: bool) -> int:
    removed = 0
    for job_id in job_ids:
        target = output_dir / job_id
        if not target.exists():
            continue
        if apply:
            shutil.rmtree(target, ignore_errors=True)
        removed += 1
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset stale local jobs for clean dev sessions.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default is dry-run).",
    )
    parser.add_argument(
        "--purge-output",
        action="store_true",
        help="Also delete output/<job_id> dirs for reset jobs.",
    )
    args = parser.parse_args()

    settings = load_settings()
    output_dir = Path(settings.output_dir)

    sql_count, sql_ids = _reset_sql_jobs(apply=args.apply)
    fs_ids = list(_iter_local_non_terminal_job_dirs(output_dir))

    if args.apply and fs_ids:
        for jid in fs_ids:
            job_file = output_dir / jid / "job.json"
            try:
                data = json.loads(job_file.read_text(encoding="utf-8"))
                data["status"] = "failed"
                data["error"] = "Local dev reset: non-terminal job reset"
                job_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass

    purge_ids = set(sql_ids) | set(fs_ids)
    removed_dirs = (
        _purge_output_dirs(output_dir, purge_ids, apply=args.apply) if args.purge_output else 0
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[dev-reset] mode={mode}")
    print(f"[dev-reset] sql_non_terminal_jobs={sql_count}")
    print(f"[dev-reset] fs_non_terminal_jobs={len(fs_ids)}")
    if args.purge_output:
        print(f"[dev-reset] output_dirs_matched={removed_dirs}")
    if not args.apply:
        print("[dev-reset] no changes applied (use --apply)")


if __name__ == "__main__":
    main()
