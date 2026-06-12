"""Authoritative expected artifact set for job finalization — Phase 3.3."""

from __future__ import annotations

ARTIFACT_KIND_EXECUTION_LOG = "execution_log"
ARTIFACT_KIND_HYBRID_REPORT_JSON = "hybrid_report_json"
ARTIFACT_KIND_HYBRID_REPORT_CSV = "hybrid_report_csv"

REQUIRED_ARTIFACT_KINDS: frozenset[str] = frozenset(
    {
        ARTIFACT_KIND_EXECUTION_LOG,
        ARTIFACT_KIND_HYBRID_REPORT_JSON,
    }
)

OPTIONAL_ARTIFACT_KINDS: frozenset[str] = frozenset({ARTIFACT_KIND_HYBRID_REPORT_CSV})

ALL_EXPECTED_ARTIFACT_KINDS: frozenset[str] = REQUIRED_ARTIFACT_KINDS | OPTIONAL_ARTIFACT_KINDS


def is_required_artifact_kind(kind: str) -> bool:
    return kind in REQUIRED_ARTIFACT_KINDS
