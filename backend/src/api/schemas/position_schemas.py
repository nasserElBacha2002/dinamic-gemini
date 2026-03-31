"""v3.0 Position/result API schemas — Épica 6.

Sprint 2 adds nested ``product``, ``quantity``, and ``traceability`` blocks. Top-level quantity /
SKU / traceability fields remain as deprecated aliases for backward compatibility.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.listing_schemas import PageMeta

_QtySourcePublic = Literal[
    "detected",
    "inferred",
    "merge_inferred",
    "manual_review",
    "label_explicit",
    "unknown",
    "consolidated",
]

_ProductIdentitySource = Literal["primary_product", "summary_technical", "summary_aggregated"]

# Aligns with frontend `TRACEABILITY_STATUSES` / `ApiTraceabilityStatus`; union with str for forward compatibility.
_TraceabilityStatusPublic = Literal["valid", "missing", "invalid", "unvalidated"]


class PositionProductBlock(BaseModel):
    """Canonical product identity for list + detail (Sprint 2)."""

    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = Field(None, description="Primary ``ProductRecord`` id when applicable.")
    sku: Optional[str] = Field(None, description="Public SKU; mirrors deprecated top-level ``sku``.")
    display_label: Optional[str] = Field(
        None,
        description="Operator-facing label: primary description, else ``review_display_label`` from snapshot.",
    )
    barcode: Optional[str] = Field(
        None,
        description="``position_barcode`` from technical snapshot when present.",
    )
    identity_source: _ProductIdentitySource = Field(
        ...,
        description="How identity was resolved; aligns with ``PositionCanonicalProduct.identity_source``.",
    )


class PositionQuantityBlock(BaseModel):
    """Canonical quantity block (Sprint 2).

    **Semantics:** ``detected`` matches legacy ``detected_quantity`` (resolved detected in v3.2.2 sense).
    ``final`` is operator-visible: ``corrected`` when set, else system-resolved ``qty`` (same rule as CSV ``final_quantity``).
    Top-level ``qty`` remains the **system-resolved** contract quantity without applying correction as override.
    """

    model_config = ConfigDict(extra="forbid")

    detected: int = Field(..., description="Resolved detected quantity (legacy `detected_quantity`).")
    corrected: Optional[int] = Field(None, description="Operator correction when present.")
    final: int = Field(
        ...,
        description="Line quantity for UX: corrected ?? system qty (see module docstring vs legacy `qty`).",
    )
    source: _QtySourcePublic = Field(..., description="Provenance; mirrors deprecated ``qtySource``.")
    inference_reason: Optional[str] = Field(None, description="Mirrors deprecated ``qtyInferenceReason``.")
    resolved: Optional[bool] = Field(None, description="Mirrors deprecated ``qtyResolved``.")


class PositionTraceabilityBlock(BaseModel):
    """Canonical traceability + evidence pointers (Sprint 2). Source image is report-level; evidence is crop linkage."""

    model_config = ConfigDict(extra="forbid")

    status: Optional[Union[_TraceabilityStatusPublic, str]] = Field(
        None,
        description=(
            "Traceability validity; mirrors deprecated ``traceability_status``. "
            "Known v3 values: valid, missing, invalid, unvalidated. "
            "Other strings may appear for forward-compatible extensions."
        ),
    )
    source_image_id: Optional[str] = Field(None, description="Report source image; mirrors deprecated field.")
    source_image_original_filename: Optional[str] = None
    primary_evidence_id: Optional[str] = Field(
        None,
        description="Primary evidence crop id; mirrors deprecated top-level ``primary_evidence_id``.",
    )
    has_evidence: bool = Field(False, description="Mirrors deprecated ``has_evidence``.")


class PositionSummaryResponse(BaseModel):
    """One row in the per-aisle results list (Aisle Results / review entry).

    **Sprint 2:** Prefer nested ``product``, ``quantity``, and ``traceability``. Top-level SKU/qty/traceability
    fields are deprecated aliases preserved for existing clients.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    aisle_id: str
    status: str
    confidence: float
    needs_review: bool
    primary_evidence_id: Optional[str] = Field(
        None,
        deprecated=True,
        description="Deprecated: use `traceability.primary_evidence_id`.",
    )
    created_at: datetime
    updated_at: datetime
    detected_summary_json: Optional[Dict[str, Any]] = None

    product: PositionProductBlock = Field(..., description="Canonical product identity (Sprint 2).")
    quantity: PositionQuantityBlock = Field(..., description="Canonical quantity (Sprint 2).")
    traceability: PositionTraceabilityBlock = Field(..., description="Canonical traceability (Sprint 2).")

    sku: Optional[str] = Field(None, deprecated=True, description="Deprecated: use `product.sku`.")
    detected_quantity: Optional[int] = Field(None, deprecated=True, description="Deprecated: use `quantity.detected`.")
    corrected_quantity: Optional[int] = Field(None, deprecated=True, description="Deprecated: use `quantity.corrected`.")
    qty: int = Field(..., deprecated=True, description="Deprecated: system-resolved qty; prefer `quantity.final` for UX line total.")
    qtySource: _QtySourcePublic = Field(..., deprecated=True, description="Deprecated: use `quantity.source`.")
    qtyInferenceReason: Optional[str] = Field(None, deprecated=True, description="Deprecated: use `quantity.inference_reason`.")
    qtyResolved: Optional[bool] = Field(None, deprecated=True, description="Deprecated: use `quantity.resolved`.")
    source_image_id: Optional[str] = Field(None, deprecated=True, description="Deprecated: use `traceability.source_image_id`.")
    traceability_status: Optional[Union[_TraceabilityStatusPublic, str]] = Field(
        None,
        deprecated=True,
        description="Deprecated: use `traceability.status` (known v3 values: valid, missing, invalid, unvalidated).",
    )
    has_evidence: bool = Field(False, deprecated=True, description="Deprecated: use `traceability.has_evidence`.")
    source_image_original_filename: Optional[str] = Field(
        None,
        deprecated=True,
        description="Deprecated: use `traceability.source_image_original_filename`.",
    )


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
