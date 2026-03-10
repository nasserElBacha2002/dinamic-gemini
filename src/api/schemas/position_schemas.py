"""v3.0 Position/result API schemas — Épica 6."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PositionSummaryResponse(BaseModel):
    """Summary of a position in list responses."""
    id: str
    aisle_id: str
    status: str
    confidence: float
    needs_review: bool
    primary_evidence_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    detected_summary_json: Optional[Dict[str, Any]] = None


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


class PositionDetailResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/positions/{position_id}."""
    position: PositionSummaryResponse
    products: List[ProductRecordResponse]
    evidences: List[EvidenceResponse]
