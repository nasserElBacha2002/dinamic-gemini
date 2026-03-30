"""
Upload durable worker outputs (Phase 3B) through ArtifactStore.

Temp run_dir files remain the execution workspace; this module copies required
artifacts to the configured provider and returns metadata for job.result_json.

Canonical logical keys (prefix-free; S3 adapter may prepend a configured prefix):
    v3/jobs/{job_id}/{run_segment}/{filename}

``run_segment`` is the pipeline run directory basename (e.g. ``"run"``), matching
local layout ``{output_dir}/{job_id}/{run_segment}/...``. There is only one path
segment for the run — never ``.../run/run/...`` (avoid ``v3/jobs/{id}/run/{run_id}``
when ``run_id`` is already the segment name).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping

from src.infrastructure.storage.artifact_store import ArtifactStore, StoredArtifact

logger = logging.getLogger(__name__)

DURABLE_ARTIFACT_KIND_EXECUTION_LOG = "execution_log"
DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON = "hybrid_report_json"
DURABLE_ARTIFACT_KIND_HYBRID_REPORT_CSV = "hybrid_report_csv"

# Default run directory basename; must match ``RUN_ID`` in ``v3_job_executor`` (single source of truth here).
DEFAULT_V3_WORKER_RUN_SEGMENT = "run"

WORKER_DURABLE_LOGICAL_PREFIX_ROOT = "v3/jobs"


def worker_durable_artifact_key_prefix(job_id: str, run_segment: str) -> str:
    """Return ``v3/jobs/{job_id}/{run_segment}`` (no trailing slash).

    All durable worker object keys for this job run share this prefix.
    """
    return f"{WORKER_DURABLE_LOGICAL_PREFIX_ROOT}/{job_id}/{run_segment}"


def worker_output_storage_keys(job_id: str, run_segment: str) -> Mapping[str, str]:
    """Logical storage keys (prefix-free) for durable worker artifacts.

    Args:
        job_id: v3 inventory job id.
        run_segment: Run directory name under the job folder (normally
            :data:`DEFAULT_V3_WORKER_RUN_SEGMENT`).
    """
    base = worker_durable_artifact_key_prefix(job_id, run_segment)
    return {
        DURABLE_ARTIFACT_KIND_EXECUTION_LOG: f"{base}/execution_log.jsonl",
        DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON: f"{base}/hybrid_report.json",
        DURABLE_ARTIFACT_KIND_HYBRID_REPORT_CSV: f"{base}/hybrid_report.csv",
    }


def stored_artifact_to_dict(stored: StoredArtifact) -> Dict[str, Any]:
    return {
        "storage_provider": stored.storage_provider,
        "storage_bucket": stored.storage_bucket,
        "storage_key": stored.storage_key,
        "content_type": stored.content_type,
        "file_size_bytes": stored.file_size_bytes,
        "etag": stored.etag,
    }


def publish_worker_durable_artifacts(
    store: ArtifactStore,
    *,
    job_id: str,
    run_segment: str,
    run_dir: Path,
) -> Dict[str, Dict[str, Any]]:
    """Upload durable artifacts from run_dir. Raises if a required file is missing or upload fails.

    Optional ``hybrid_report.csv`` is uploaded only when present (pipeline always generates it in normal runs).
    """
    keys = worker_output_storage_keys(job_id, run_segment)
    run_dir = Path(run_dir)
    out: Dict[str, Dict[str, Any]] = {}

    specs: list[tuple[str, Path, str, bool]] = [
        (
            DURABLE_ARTIFACT_KIND_EXECUTION_LOG,
            run_dir / "execution_log.jsonl",
            "application/x-ndjson",
            True,
        ),
        (
            DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON,
            run_dir / "hybrid_report.json",
            "application/json",
            True,
        ),
        (
            DURABLE_ARTIFACT_KIND_HYBRID_REPORT_CSV,
            run_dir / "hybrid_report.csv",
            "text/csv",
            False,
        ),
    ]

    for kind, path, content_type, required in specs:
        logical_key = keys[kind]
        if not path.is_file():
            if required:
                raise FileNotFoundError(
                    f"Required durable artifact missing before upload: {path.name} "
                    f"(job_id={job_id} run_segment={run_segment})"
                )
            logger.info(
                "worker_durable_artifact_skip_missing",
                extra={
                    "job_id": job_id,
                    "run_segment": run_segment,
                    "artifact_kind": kind,
                    "path": str(path),
                },
            )
            continue

        size = path.stat().st_size
        logger.info(
            "worker_durable_artifact_upload_start",
            extra={
                "job_id": job_id,
                "run_segment": run_segment,
                "artifact_kind": kind,
                "storage_key": logical_key,
                "local_path": str(path),
                "file_size_bytes": size,
            },
        )
        with open(path, "rb") as fh:
            stored = store.put_object(logical_key, fh, content_type)

        logger.info(
            "worker_durable_artifact_upload_ok",
            extra={
                "job_id": job_id,
                "run_segment": run_segment,
                "artifact_kind": kind,
                "storage_provider": stored.storage_provider,
                "storage_bucket": stored.storage_bucket,
                "storage_key": stored.storage_key,
                "content_type": stored.content_type,
                "file_size_bytes": stored.file_size_bytes,
                "etag": stored.etag,
            },
        )
        out[kind] = stored_artifact_to_dict(stored)

    return out


def merge_durable_into_result_json(
    base: MutableMapping[str, Any],
    durable_artifacts: Mapping[str, Mapping[str, Any]],
) -> None:
    """Attach ``durable_artifacts`` to a job result_json mapping (mutates ``base``)."""
    if not durable_artifacts:
        return
    base["durable_artifacts"] = dict(durable_artifacts)
