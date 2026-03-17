"""
Label entities — v3.2.3.

RawLabel: original detected/interpreted observation (no merge).
NormalizedLabel: one or more raw labels after merge evaluation.
FinalCountRecord: final business output consumed by API/reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class RawLabel:
    """Original observation before any consolidation. Never overwritten."""

    id: str
    inventory_id: str
    aisle_id: str
    position_id: Optional[str]
    evidence_id: Optional[str]
    group_key: str
    provider: str
    source_type: str
    source_reference: Optional[str]
    sku_raw: Optional[str]
    sku_candidate: Optional[str]
    product_name_raw: Optional[str]
    detected_text: Optional[str]
    confidence: Optional[float]
    metadata: Dict[str, Any]
    created_at: datetime


@dataclass
class NormalizedLabel:
    """One or more raw labels after merge evaluation. Traceability via raw_label_ids."""

    id: str
    inventory_id: str
    aisle_id: str
    position_id: Optional[str]
    group_key: str
    canonical_sku: Optional[str]
    canonical_product_name: Optional[str]
    raw_label_ids: List[str]
    merge_rule_applied: str
    merge_confidence: Optional[float]
    merge_reason: str
    review_required: bool
    metadata: Dict[str, Any]
    created_at: datetime


@dataclass
class FinalCountRecord:
    """Final business output: consolidated quantity per position/SKU."""

    id: str
    inventory_id: str
    aisle_id: str
    position_id: Optional[str]
    sku: Optional[str]
    product_name: Optional[str]
    quantity: int
    normalized_label_ids: List[str]
    review_required: bool
    explanation_summary: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime
