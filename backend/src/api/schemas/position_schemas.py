"""v3.0 Position/result API schemas — Épica 6."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.api.schemas.listing_schemas import PageMeta


class PositionSummaryResponse(BaseModel):
    """One row in the per-aisle results list (Aisle Results / review entry).

    Same shape as the ``position`` field on detail responses. Quantity fields follow the v3.2.2
    contract (``qty``, ``qtySource``, ``qtyResolved``); ``needs_review`` and ``status`` drive review UX;
    ``has_evidence`` and ``traceability_status`` avoid inferring from raw JSON in the client.
    """
    id: str
    aisle_id: str
    status: str
    confidence: float
    needs_review: bool
    primary_evidence_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    detected_summary_json: Optional[Dict[str, Any]] = None
    sku: Optional[str] = None
    detected_quantity: Optional[int] = None
    corrected_quantity: Optional[int] = None
    # v3.2.2 — stable qty contract; required so response building never relies on defaults
    qty: int
    qtySource: Literal[
        "detected",
        "inferred",
        "merge_inferred",
        "manual_review",
        "label_explicit",
        "unknown",
        "consolidated",
    ]
    qtyInferenceReason: Optional[str] = None
    """v3.2.2: When True/False, qty is from resolved decision; when None, legacy/compatibility path."""
    qtyResolved: Optional[bool] = None
    """Epic 3.1.B: image_id of source image for this position (from report entity)."""
    source_image_id: Optional[str] = None
    """Epic 3.1.B: valid | missing | invalid | unvalidated (from report entity)."""
    traceability_status: Optional[str] = None
    """Epic 2: explicit flag so frontend does not infer from primary_evidence_id. True when primary_evidence_id is set."""
    has_evidence: bool = False
    """Epic 2 / Epic 5: original filename of source image when available (photos jobs). From report/summary."""
    source_image_original_filename: Optional[str] = None


class PositionListResponse(PageMeta):
    """Response for GET .../aisles/{aisle_id}/positions (Aisle Results).

    **Consolidation vs pagination:** filters apply to **raw** rows; ``page`` / ``page_size`` /
    ``sort_by`` / ``sort_dir`` apply **after** SKU consolidation within the raw rows the server
    loaded.

    **Truncation:** the server loads at most ``V3_POSITIONS_AISLE_RAW_CAP`` raw rows before
    consolidating. When ``raw_fetch_truncated`` is ``true``, more raw rows likely exist in the
    aisle than were loaded. In that case ``total_items`` and ``total_pages`` count **only**
    consolidated rows built from that loaded window — they are **not** guaranteed to match the
    full aisle. UIs must not treat them as globally exact totals; prefer showing a warning or
    disabling “last page” semantics when ``raw_fetch_truncated`` is true until a future true-count
    or streaming strategy exists.
    """

    positions: List[PositionSummaryResponse]
    raw_fetch_truncated: bool = Field(
        False,
        description=(
            "True when the raw fetch reached the configured cap; total_items/total_pages are then "
            "only meaningful within that fetch window, not for the full aisle."
        ),
    )


class ProductRecordResponse(BaseModel):
    """Product record within a position."""
    id: str
    position_id: str
    sku: str
    description: Optional[str] = None
    detected_quantity: int
    corrected_quantity: Optional[int] = None
    confidence: float
    created_at: datetime
    updated_at: datetime


class EvidenceResponse(BaseModel):
    """Evidence (crop/media) for a position."""
    id: str
    entity_type: str
    entity_id: str
    type: str
    storage_path: str
    source_asset_id: Optional[str] = None
    is_primary: bool
    frame_index: Optional[int] = None
    timestamp_ms: Optional[int] = None
    bbox_json: Optional[Dict[str, Any]] = None
    quality_score: Optional[float] = None


class ReviewActionResponse(BaseModel):
    """Single review action in audit history."""
    id: str
    position_id: str
    action_type: str
    before_json: Dict[str, Any]
    after_json: Dict[str, Any]
    created_at: datetime
    user_id: Optional[str] = None
    comment: Optional[str] = None


class PositionDetailResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/positions/{position_id}.
    v3.1.1: Result is the only visible review object; products are no longer returned."""
    position: PositionSummaryResponse
    evidences: List[EvidenceResponse]
    review_actions: List[ReviewActionResponse] = Field(default_factory=list)


ReviewActionTypeLiteral = Literal["confirm", "update_quantity", "update_sku", "delete_position"]


class ReviewActionRequest(BaseModel):
    """Request body for POST .../positions/{position_id}/reviews. Fields required depend on action_type.
    user_id and comment are reserved for future use (not used in Épica 8)."""
    action_type: ReviewActionTypeLiteral
    product_id: Optional[str] = None
    corrected_quantity: Optional[int] = None
    sku: Optional[str] = None
    description: Optional[str] = None
