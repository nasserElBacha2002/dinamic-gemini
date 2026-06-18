"""Inspect durable artifact publication state for a job (outbox, manifest, staging)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _print_section(title: str, payload: object) -> None:
    print(f"\n== {title} ==")
    print(json.dumps(payload, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Debug durable artifact publication for a job")
    parser.add_argument("--job-id", required=True, help="Inventory job UUID")
    args = parser.parse_args(argv)
    job_id = args.job_id.strip()

    try:
        from src.runtime.app_container import get_app_container
    except ImportError as exc:
        print(f"Cannot load app container: {exc}", file=sys.stderr)
        return 2

    container = get_app_container()
    outbox_store = container.artifact_publication_outbox_store
    manifest_store = container.artifact_manifest_store
    staging_store = container.artifact_staging_store

    if outbox_store is None:
        print("artifact_publication_outbox_store is not configured", file=sys.stderr)
        return 2

    from src.application.services.artifact_publication_diagnostics import (
        failed_outbox_entry_summary,
    )

    outbox_entries = [
        failed_outbox_entry_summary(entry) for entry in outbox_store.list_entries(job_id)
    ]
    _print_section("outbox_entries", outbox_entries)

    manifest_entries: list[dict] = []
    if manifest_store is not None:
        for kind in ("execution_log", "hybrid_report_json", "hybrid_report_csv"):
            entry = manifest_store.get_entry(job_id, kind)
            if entry is None:
                continue
            manifest_entries.append(
                {
                    "artifact_kind": entry.artifact_kind,
                    "status": entry.status.value if hasattr(entry.status, "value") else str(entry.status),
                    "storage_key": entry.storage_key,
                    "size_bytes": entry.size_bytes,
                    "source_sha256": entry.source_sha256,
                    "error": entry.error,
                }
            )
    _print_section("manifest_entries", manifest_entries)

    staging_status: list[dict] = []
    if staging_store is not None:
        for row in outbox_entries:
            ref = row.get("source_reference")
            if not ref:
                continue
            staging_status.append(
                {
                    "artifact_kind": row.get("artifact_kind"),
                    "staging_key": ref,
                    "exists": staging_store.source_exists(ref),
                    "size_bytes": staging_store.source_size(ref) if staging_store.source_exists(ref) else None,
                    "sha256": staging_store.source_checksum(ref) if staging_store.source_exists(ref) else None,
                }
            )
    _print_section("staging_status", staging_status)

    try:
        summary = outbox_store.summary_for_job(job_id)
        _print_section(
            "summary",
            {
                "required_total": summary.required_total,
                "required_published": summary.required_published,
                "pending": summary.pending,
                "retry_scheduled": summary.retry_scheduled,
                "permanently_failed": summary.permanently_failed,
                "next_attempt_at": summary.next_attempt_at,
            },
        )
    except Exception as exc:
        _print_section("summary_error", {"error": str(exc)})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
