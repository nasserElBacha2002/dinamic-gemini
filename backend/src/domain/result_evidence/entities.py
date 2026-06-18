"""Phase 4.6 — structural entity traceability evidence persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ResultEvidenceRole(str, Enum):
    PRIMARY_EVIDENCE = "primary_evidence"
    REFERENCE_IMAGE = "reference_image"
    UNKNOWN = "unknown"


RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY = "entity_traceability"


@dataclass
class ResultEvidenceRecord:
    """Queryable traceability evidence for one detected entity in a job execution."""

    id: str
    job_id: str
    inventory_id: str
    aisle_id: str
    position_id: str | None
    entity_uid: str | None
    model_entity_id: str | None
    raw_manifest_entry_id: str | None
    manifest_entry_id: str | None
    raw_source_image_id: str | None
    resolved_manifest_entry_id: str | None
    source_image_id: str | None
    source_asset_id: str | None
    traceability_status: str | None
    traceability_warning: str | None
    role: ResultEvidenceRole | None
    provider: str | None
    model_name: str | None
    schema_version: str | None
    manifest_version: int | None
    has_valid_evidence: bool
    evidence_kind: str
    created_at: datetime
    updated_at: datetime
