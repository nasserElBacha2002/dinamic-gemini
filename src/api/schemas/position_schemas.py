"""v3.0 Position/result API schemas — Épica 6."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class PositionSummaryResponse(BaseModel):
    """Summary of a position in list responses. Includes optional sku and detected_quantity when derivable from the result summary."""
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
    """Epic 3.1.B: image_id of source image for this position (from report entity)."""
    source_image_id: Optional[str] = None
    """Epic 3.1.B: valid | missing | invalid | unvalidated (from report entity)."""
    traceability_status: Optional[str] = None


class PositionListResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/positions."""
    positions: List[PositionSummaryResponse]


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
    """Response for GET .../aisles/{aisle_id}/positions/{position_id}."""
    position: PositionSummaryResponse
    products: List[ProductRecordResponse]
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
