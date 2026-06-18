"""Authoritative expected artifact set for job finalization — Phase 3.3."""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.jobs.artifact_manifest import ArtifactManifestEntry, ArtifactManifestStatus

ARTIFACT_KIND_EXECUTION_LOG = "execution_log"
ARTIFACT_KIND_HYBRID_REPORT_JSON = "hybrid_report_json"
ARTIFACT_KIND_HYBRID_REPORT_CSV = "hybrid_report_csv"
ARTIFACT_KIND_TRACEABILITY_MANIFEST = "traceability_manifest"

REQUIRED_ARTIFACT_KINDS: frozenset[str] = frozenset(
    {
        ARTIFACT_KIND_EXECUTION_LOG,
        ARTIFACT_KIND_HYBRID_REPORT_JSON,
    }
)

OPTIONAL_ARTIFACT_KINDS: frozenset[str] = frozenset(
    {
        ARTIFACT_KIND_HYBRID_REPORT_CSV,
        ARTIFACT_KIND_TRACEABILITY_MANIFEST,
    }
)

ALL_EXPECTED_ARTIFACT_KINDS: frozenset[str] = REQUIRED_ARTIFACT_KINDS | OPTIONAL_ARTIFACT_KINDS


def is_required_artifact_kind(kind: str, *, entry_required: bool | None = None) -> bool:
    if entry_required is not None:
        return entry_required
    return kind in REQUIRED_ARTIFACT_KINDS


def artifact_manifest_required_kinds_published(
    entries: Sequence[ArtifactManifestEntry],
) -> bool:
    """True when all static and dynamic required manifest entries are published."""
    by_kind = {entry.artifact_kind: entry for entry in entries}
    for kind in REQUIRED_ARTIFACT_KINDS:
        entry = by_kind.get(kind)
        if (
            entry is None
            or not entry.required
            or entry.status != ArtifactManifestStatus.PUBLISHED
        ):
            return False
    for entry in entries:
        if entry.required and entry.status != ArtifactManifestStatus.PUBLISHED:
            return False
    return True


def artifact_manifest_missing_required_kinds(
    entries: Sequence[ArtifactManifestEntry],
) -> set[str]:
    """Static required kinds plus any manifest row marked required but not published."""
    by_kind = {entry.artifact_kind: entry for entry in entries}
    missing: set[str] = set()
    for kind in REQUIRED_ARTIFACT_KINDS:
        entry = by_kind.get(kind)
        if (
            entry is None
            or not entry.required
            or entry.status != ArtifactManifestStatus.PUBLISHED
        ):
            missing.add(kind)
    for entry in entries:
        if entry.required and entry.status != ArtifactManifestStatus.PUBLISHED:
            missing.add(entry.artifact_kind)
    return missing
