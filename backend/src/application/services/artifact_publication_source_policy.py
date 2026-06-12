"""Source durability policy per artifact kind — Phase 3.5."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_CSV,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    is_required_artifact_kind,
)
from src.domain.jobs.artifact_publication_outbox import ArtifactSourceType
from src.infrastructure.pipeline.worker_durable_artifact_publisher import worker_output_storage_keys

_KIND_TO_FILENAME = {
    ARTIFACT_KIND_EXECUTION_LOG: "execution_log.jsonl",
    ARTIFACT_KIND_HYBRID_REPORT_JSON: "hybrid_report.json",
    ARTIFACT_KIND_HYBRID_REPORT_CSV: "hybrid_report.csv",
}

_CONTENT_TYPES = {
    ARTIFACT_KIND_EXECUTION_LOG: "application/x-ndjson",
    ARTIFACT_KIND_HYBRID_REPORT_JSON: "application/json",
    ARTIFACT_KIND_HYBRID_REPORT_CSV: "text/csv",
}


@dataclass(frozen=True)
class ResolvedArtifactSource:
    artifact_kind: str
    required: bool
    source_type: ArtifactSourceType
    local_path: Path | None
    destination_key: str
    content_type: str
    size_bytes: int | None
    content_hash: str | None
    source_reference: str | None


def classify_source_type(artifact_kind: str) -> ArtifactSourceType:
    if artifact_kind == ARTIFACT_KIND_HYBRID_REPORT_CSV:
        return ArtifactSourceType.RECONSTRUCTABLE
    if artifact_kind in (ARTIFACT_KIND_EXECUTION_LOG, ARTIFACT_KIND_HYBRID_REPORT_JSON):
        return ArtifactSourceType.EXACT_LOCAL_SOURCE
    return ArtifactSourceType.UNAVAILABLE


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_local_source(
    *,
    job_id: str,
    artifact_kind: str,
    run_segment: str,
    run_dir: Path,
    source_paths: dict[str, Path] | None = None,
) -> ResolvedArtifactSource:
    required = is_required_artifact_kind(artifact_kind)
    destination_key = worker_output_storage_keys(job_id, run_segment)[artifact_kind]
    content_type = _CONTENT_TYPES.get(artifact_kind, "application/octet-stream")
    source_type = classify_source_type(artifact_kind)
    filename = _KIND_TO_FILENAME.get(artifact_kind)
    if filename is None:
        return ResolvedArtifactSource(
            artifact_kind=artifact_kind,
            required=required,
            source_type=ArtifactSourceType.UNAVAILABLE,
            local_path=None,
            destination_key=destination_key,
            content_type=content_type,
            size_bytes=None,
            content_hash=None,
            source_reference=None,
        )
    local_path = (source_paths or {}).get(artifact_kind) or (Path(run_dir) / filename)
    if not local_path.is_file():
        if required:
            return ResolvedArtifactSource(
                artifact_kind=artifact_kind,
                required=required,
                source_type=ArtifactSourceType.UNAVAILABLE,
                local_path=None,
                destination_key=destination_key,
                content_type=content_type,
                size_bytes=None,
                content_hash=None,
                source_reference=str(local_path),
            )
        return ResolvedArtifactSource(
            artifact_kind=artifact_kind,
            required=required,
            source_type=ArtifactSourceType.UNAVAILABLE,
            local_path=None,
            destination_key=destination_key,
            content_type=content_type,
            size_bytes=None,
            content_hash=None,
            source_reference=str(local_path),
        )
    size = local_path.stat().st_size
    content_hash = _sha256_file(local_path)
    return ResolvedArtifactSource(
        artifact_kind=artifact_kind,
        required=required,
        source_type=source_type,
        local_path=local_path,
        destination_key=destination_key,
        content_type=content_type,
        size_bytes=size,
        content_hash=content_hash,
        source_reference=str(local_path),
    )
