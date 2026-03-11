"""
Entity domain model for hybrid v2.1 (structural, label-aware).

Replaces pallet-centric view with entity types: PALLET, EMPTY_PALLET, LOOSE_BOXES.
"""

from dataclasses import dataclass
from typing import List, Optional

# Allowed entity types and count statuses for validation
ENTITY_TYPES = ("PALLET", "EMPTY_PALLET", "LOOSE_BOXES")
COUNT_STATUSES = (
    "COUNTED",
    "NEEDS_REVIEW",
    "NOT_COUNTABLE",
    "EMPTY",
    "INVALID_STRUCTURE",
)


@dataclass
class Entity:
    """Logistic entity detected in global analysis (v2.1)."""

    # Stable internal id: job_id + model_entity_id (for API when pallet_id is duplicated)
    entity_uid: str
    entity_type: str  # PALLET | EMPTY_PALLET | LOOSE_BOXES
    model_entity_id: str
    # Position (no position_label_text: Gemini no lo devuelve para reducir coste/tokens)
    position_barcode: Optional[str] = None
    position_label_bbox: Optional[List[float]] = None  # [x1, y1, x2, y2] normalized 0..1
    # Product (internal code replaces long product label text)
    internal_code: Optional[str] = None
    product_label_quantity: Optional[int] = None
    product_label_bbox: Optional[List[float]] = None  # [x1, y1, x2, y2] normalized 0..1
    # Structure
    has_boxes: bool = False
    confidence: float = 0.0
    # Resolved identity (set by resolve_pallet_id)
    pallet_id: Optional[str] = None
    pallet_id_method: Optional[str] = None
    # Status (set by assign_count_status)
    count_status: Optional[str] = None
    final_quantity: Optional[int] = None
    # Duplicate barcode conflict (set by resolve_pallet_id)
    conflict_flag: bool = False
    conflict_reason: Optional[str] = None
    # Local quality score [0..1] (set by compute_entity_quality_score)
    entity_quality_score: float = 0.0
    # Evidence pack (set by generate_evidence_pack)
    evidence_path: Optional[str] = None  # relative path to run/evidence/<slug>/
    evidence_localization: Optional[str] = None  # "LOCALIZED" | "UNLOCALIZED"
    # Original JSON index for deterministic sort tie-breaker
    original_index: int = 0
    # Epic 3.1.B: image traceability (parsed from provider; validated against job images)
    source_image_id: Optional[str] = None
    traceability_status: Optional[str] = None  # one of TraceabilityStatus (valid, missing, invalid, unvalidated)
    traceability_warning: Optional[str] = None  # diagnostic only: report + API; not persisted to pallet_results
