"""Phase 4.8 — API schemas for structural result_evidence contract."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

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
    traceability_warning: Optional[str] = None
    role: Optional[str] = None
    source_image_id: Optional[str] = None
    source_asset_id: Optional[str] = None
    resolved_manifest_entry_id: Optional[str] = None
    raw_manifest_entry_id: Optional[str] = None
    raw_source_image_id: Optional[str] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    image_access_status: Optional[ImageAccessStatusLiteral | str] = None
    source_kind: EvidenceSourceKindLiteral | str
    provider: Optional[str] = None
    model_name: Optional[str] = None


class TraceabilityArtifactMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    published: bool
    required: bool
    status: str
    storage_key: Optional[str] = None
    content_hash: Optional[str] = None
    size_bytes: Optional[int] = None
    published_at: Optional[datetime] = None


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
    manifest_unavailable: int = 0
    manifest_invalid: int = 0
    artifact_published: int = 0


class JobTraceabilityEntityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_id: Optional[str] = None
    entity_uid: Optional[str] = None
    model_entity_id: Optional[str] = None
    evidence: ResultEvidenceViewResponse


class JobTraceabilityResponse(BaseModel):
    """GET .../jobs/{job_id}/traceability"""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    inventory_id: str
    aisle_id: str
    traceability: dict[str, object] = Field(
        ...,
        description="Traceability envelope with status, artifact metadata, and summary.",
    )
    entities: list[JobTraceabilityEntityResponse] = Field(default_factory=list)
