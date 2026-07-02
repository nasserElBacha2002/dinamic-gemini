"""Phase 4.8 — API schemas for structural result_evidence contract."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceTraceabilityStatusLiteral = Literal[
    "valid",
    "invalid",
    "missing",
    "unvalidated",
    "legacy_unavailable",
    "artifact_unavailable",
]

EvidenceSourceKindLiteral = Literal[
    "structural_result_evidence",
    "legacy_json",
    "unavailable",
]

ImageAccessStatusLiteral = Literal[
    "available",
    "url_unavailable",
    "not_allowed",
]


class ResultEvidenceViewResponse(BaseModel):
    """Fail-closed evidence contract for one result entity."""

    model_config = ConfigDict(extra="forbid")

    displayable: bool
    traceability_status: EvidenceTraceabilityStatusLiteral | str
    traceability_warning: str | None = None
    role: str | None = None
    source_image_id: str | None = None
    source_asset_id: str | None = None
    resolved_manifest_entry_id: str | None = None
    raw_manifest_entry_id: str | None = None
    raw_source_image_id: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    image_access_status: ImageAccessStatusLiteral | str | None = None
    source_kind: EvidenceSourceKindLiteral | str
    provider: str | None = None
    model_name: str | None = None
    review_context_displayable: bool = False
    review_context_image_url: str | None = None
    review_context_warning: str | None = None


class TraceabilityArtifactMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    published: bool
    required: bool
    status: str
    storage_key: str | None = None
    content_hash: str | None = None
    size_bytes: int | None = None
    published_at: datetime | None = None


class TraceabilitySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_evidence_rows: int = 0
    valid: int = 0
    invalid: int = 0
    missing: int = 0
    unvalidated: int = 0
    displayable: int = 0
    not_displayable: int = 0
    reference_rejected: int = 0
    unknown_identifier: int = 0
    conflicting_identifier: int = 0
    malformed_identifier: int = 0
    manifest_unavailable: int = 0
    manifest_invalid: int = 0
    unvalidated_unknown: int = 0
    artifact_required: int = 0
    artifact_published: int = 0


class JobTraceabilityEnvelopeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "artifact_unavailable", "legacy_unavailable"] | str
    artifact: TraceabilityArtifactMetadataResponse | None = None
    summary: TraceabilitySummaryResponse


class JobTraceabilityEntityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_id: str | None = None
    entity_uid: str | None = None
    model_entity_id: str | None = None
    evidence: ResultEvidenceViewResponse


class JobTraceabilityResponse(BaseModel):
    """GET .../jobs/{job_id}/traceability"""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    inventory_id: str
    aisle_id: str
    traceability: JobTraceabilityEnvelopeResponse
    entities: list[JobTraceabilityEntityResponse] = Field(default_factory=list)
