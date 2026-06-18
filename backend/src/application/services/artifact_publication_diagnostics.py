"""Structured diagnostics for durable artifact publication — Phase 4.4 hotfix."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.domain.jobs.artifact_publication_outbox import ArtifactPublicationOutboxEntry

logger = logging.getLogger(__name__)


def failed_outbox_entry_summary(entry: ArtifactPublicationOutboxEntry) -> dict[str, Any]:
    return {
        "artifact_kind": entry.artifact_kind,
        "outbox_entry_id": entry.id,
        "status": entry.status.value,
        "attempt_count": entry.attempt_count,
        "max_attempts": entry.max_attempts,
        "last_error_code": entry.last_error_code,
        "last_error_message": entry.last_error_message,
        "source_type": entry.source_type.value,
        "source_reference": entry.source_reference,
        "destination_key": entry.destination_key,
        "source_sha256": entry.source_sha256,
        "size_bytes": entry.size_bytes,
    }


def publication_step_context(
    *,
    job_id: str,
    artifact_kind: str,
    publication_step: str,
    run_segment: str | None = None,
    local_path: Path | None = None,
    destination_key: str | None = None,
    source_type: str | None = None,
    source_reference: str | None = None,
    staging_key: str | None = None,
    outbox_entry: ArtifactPublicationOutboxEntry | None = None,
    local_size_bytes: int | None = None,
    local_sha256: str | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "job_id": job_id,
        "artifact_kind": artifact_kind,
        "publication_step": publication_step,
    }
    if run_segment is not None:
        ctx["run_segment"] = run_segment
    if local_path is not None:
        ctx["resolved_local_path"] = str(local_path)
        ctx["local_path_exists"] = local_path.is_file()
    if local_size_bytes is not None:
        ctx["local_size_bytes"] = local_size_bytes
    if local_sha256 is not None:
        ctx["local_sha256"] = local_sha256
    if destination_key is not None:
        ctx["destination_key"] = destination_key
    if source_type is not None:
        ctx["source_type"] = source_type
    if source_reference is not None:
        ctx["source_reference"] = source_reference
    if staging_key is not None:
        ctx["staging_key"] = staging_key
    if outbox_entry is not None:
        ctx["outbox_entry_id"] = outbox_entry.id
        ctx["outbox_status"] = outbox_entry.status.value
        ctx["attempt_count"] = outbox_entry.attempt_count
        ctx["max_attempts"] = outbox_entry.max_attempts
        ctx["last_error_code"] = outbox_entry.last_error_code
        ctx["last_error_message"] = outbox_entry.last_error_message
    return ctx


def log_publication_step(level: int, message: str, **context: Any) -> None:
    parts = [f"{key}={value}" for key, value in sorted(context.items()) if value is not None]
    logger.log(level, "%s %s", message, " ".join(parts))
