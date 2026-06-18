"""Artifact manifest store required-kind semantics — Phase 4.7 corrections."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.domain.jobs.artifact_manifest import ArtifactManifestEntry, ArtifactManifestStatus
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    ARTIFACT_KIND_TRACEABILITY_MANIFEST,
    artifact_manifest_missing_required_kinds,
    artifact_manifest_required_kinds_published,
)
from src.infrastructure.persistence.memory_artifact_manifest_store import (
    MemoryArtifactManifestStore,
)
from src.infrastructure.persistence.sql_artifact_manifest_store import SqlArtifactManifestStore


def _now() -> datetime:
    return datetime(2026, 6, 18, tzinfo=timezone.utc)


def _published(kind: str, *, required: bool = True) -> ArtifactManifestEntry:
    now = _now()
    return ArtifactManifestEntry(
        job_id="job-1",
        artifact_kind=kind,
        required=required,
        status=ArtifactManifestStatus.PUBLISHED,
        storage_key=f"jobs/job-1/run/{kind}",
        published_at=now,
        created_at=now,
        updated_at=now,
    )


def _pending(kind: str, *, required: bool = True) -> ArtifactManifestEntry:
    now = _now()
    return ArtifactManifestEntry(
        job_id="job-1",
        artifact_kind=kind,
        required=required,
        status=ArtifactManifestStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


def test_static_required_missing_from_rows_not_published() -> None:
    entries = [_published(ARTIFACT_KIND_EXECUTION_LOG)]
    assert artifact_manifest_required_kinds_published(entries) is False
    assert ARTIFACT_KIND_HYBRID_REPORT_JSON in artifact_manifest_missing_required_kinds(entries)


def test_execution_log_published_hybrid_report_missing_not_complete() -> None:
    entries = [_published(ARTIFACT_KIND_EXECUTION_LOG)]
    assert artifact_manifest_required_kinds_published(entries) is False
    missing = artifact_manifest_missing_required_kinds(entries)
    assert ARTIFACT_KIND_HYBRID_REPORT_JSON in missing


def test_static_required_published_traceability_required_pending_not_complete() -> None:
    entries = [
        _published(ARTIFACT_KIND_EXECUTION_LOG),
        _published(ARTIFACT_KIND_HYBRID_REPORT_JSON),
        _pending(ARTIFACT_KIND_TRACEABILITY_MANIFEST, required=True),
    ]
    assert artifact_manifest_required_kinds_published(entries) is False
    assert ARTIFACT_KIND_TRACEABILITY_MANIFEST in artifact_manifest_missing_required_kinds(entries)


def test_all_static_and_dynamic_required_published_complete() -> None:
    entries = [
        _published(ARTIFACT_KIND_EXECUTION_LOG),
        _published(ARTIFACT_KIND_HYBRID_REPORT_JSON),
        _published(ARTIFACT_KIND_TRACEABILITY_MANIFEST, required=True),
    ]
    assert artifact_manifest_required_kinds_published(entries) is True
    assert artifact_manifest_missing_required_kinds(entries) == set()


def test_memory_store_static_and_dynamic_required_semantics() -> None:
    store = MemoryArtifactManifestStore()
    now = _now()
    store.ensure_expected_entries("job-mem", now=now)
    store.mark_published(
        job_id="job-mem",
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        storage_key="k1",
        size_bytes=1,
        content_hash=None,
        required=True,
        now=now,
    )
    assert store.required_kinds_published("job-mem") is False
    assert ARTIFACT_KIND_HYBRID_REPORT_JSON in store.missing_required_kinds("job-mem")

    store.mark_published(
        job_id="job-mem",
        artifact_kind=ARTIFACT_KIND_HYBRID_REPORT_JSON,
        storage_key="k2",
        size_bytes=1,
        content_hash=None,
        required=True,
        now=now,
    )
    trace_entry = store.get_entry("job-mem", ARTIFACT_KIND_TRACEABILITY_MANIFEST)
    store.mark_pending(
        job_id="job-mem",
        artifact_kind=ARTIFACT_KIND_TRACEABILITY_MANIFEST,
        required=True,
        now=now,
        expected_version=trace_entry.version if trace_entry else None,
    )
    assert store.required_kinds_published("job-mem") is False
    assert ARTIFACT_KIND_TRACEABILITY_MANIFEST in store.missing_required_kinds("job-mem")

    store.mark_published(
        job_id="job-mem",
        artifact_kind=ARTIFACT_KIND_TRACEABILITY_MANIFEST,
        storage_key="k3",
        size_bytes=1,
        content_hash=None,
        required=True,
        now=now,
        expected_version=store.get_entry("job-mem", ARTIFACT_KIND_TRACEABILITY_MANIFEST).version,
    )
    assert store.required_kinds_published("job-mem") is True
    assert store.missing_required_kinds("job-mem") == set()


def test_sql_store_delegates_required_semantics_to_shared_policy() -> None:
    store = SqlArtifactManifestStore(MagicMock())
    entries = [
        _published(ARTIFACT_KIND_EXECUTION_LOG),
        _pending(ARTIFACT_KIND_HYBRID_REPORT_JSON, required=True),
        _pending(ARTIFACT_KIND_TRACEABILITY_MANIFEST, required=True),
    ]
    with patch.object(store, "list_entries", return_value=entries):
        assert store.required_kinds_published("job-sql") is False
        missing = store.missing_required_kinds("job-sql")
    assert missing == {
        ARTIFACT_KIND_HYBRID_REPORT_JSON,
        ARTIFACT_KIND_TRACEABILITY_MANIFEST,
    }


def test_dynamic_traceability_failed_included_in_missing_required_kinds() -> None:
    now = _now()
    entries = [
        _published(ARTIFACT_KIND_EXECUTION_LOG),
        _published(ARTIFACT_KIND_HYBRID_REPORT_JSON),
        ArtifactManifestEntry(
            job_id="job-1",
            artifact_kind=ARTIFACT_KIND_TRACEABILITY_MANIFEST,
            required=True,
            status=ArtifactManifestStatus.FAILED,
            last_error="upload failed",
            created_at=now,
            updated_at=now,
        ),
    ]
    missing = artifact_manifest_missing_required_kinds(entries)
    assert ARTIFACT_KIND_TRACEABILITY_MANIFEST in missing
