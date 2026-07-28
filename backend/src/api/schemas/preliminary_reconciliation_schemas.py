"""API schemas for preliminary vs remote reconciliation (Phase 5 corrections)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReconcilePreliminaryDetectionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1, max_length=36)
    enqueue_limit: int = Field(default=200, ge=1, le=500)


class ReconcilePreliminaryDetectionsResponse(BaseModel):
    accepted: bool
    batch_id: str
    enqueued: int
    already_terminal: int
    reconciliation_ids: list[str] = Field(default_factory=list)
    status: str = "accepted"


class PreliminaryReconciliationItem(BaseModel):
    id: str
    preliminary_detection_id: str
    asset_id: str
    remote_result_id: str | None = None
    job_id: str
    inventory_id: str
    aisle_id: str
    client_file_id: str
    local_status: str
    local_internal_code: str | None = None
    local_quantity: int | None = None
    remote_status: str | None = None
    remote_internal_code: str | None = None
    remote_quantity: int | None = None
    outcome: str
    not_comparable_reason: str | None = None
    local_parser_version: str | None = None
    local_detector_version: str | None = None
    remote_pipeline_version: str | None = None
    local_detected_at: datetime | None = None
    remote_completed_at: datetime | None = None
    compared_at: datetime
    comparison_version: str
    reconciliation_status: str
    remote_result_fingerprint: str | None = None
    revision: int = 1


class ReconciliationMetricsResponse(BaseModel):
    total_eligible_drafts: int
    total_reconciled: int
    total_pending: int
    total_not_comparable: int
    mapping_comparable: int
    code_comparable: int
    quantity_comparable: int
    code_match_count: int
    code_mismatch_count: int
    quantity_match_count: int
    quantity_mismatch_count: int
    local_only_count: int
    remote_only_count: int
    ambiguous_count: int
    both_unresolved_count: int
    comparability_rate: float | None = None
    server_code_agreement_rate: float | None = None
    quantity_agreement_rate: float | None = None
    local_only_rate: float | None = None
    remote_only_rate: float | None = None
    ambiguity_rate: float | None = None
    numerator_agreement: int
    denominator_comparable: int


class ListPreliminaryReconciliationsResponse(BaseModel):
    items: list[PreliminaryReconciliationItem]
    total: int
    metrics: ReconciliationMetricsResponse
    authority_notice: str = (
        "El resultado del servidor sigue siendo el resultado operativo."
    )
