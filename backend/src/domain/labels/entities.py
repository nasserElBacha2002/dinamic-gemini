"""
Label entities — v3.2.3.

RawLabel: original detected/interpreted observation (no merge).
NormalizedLabel: one or more raw labels after merge evaluation.
FinalCountRecord: final business output consumed by API/reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class RawLabel:
    """Original observation before any consolidation. Never overwritten."""

    id: str
    inventory_id: str
    aisle_id: str
    position_id: str | None
    evidence_id: str | None
    group_key: str
    provider: str
    source_type: str
    source_reference: str | None
    sku_raw: str | None
    sku_candidate: str | None
    product_name_raw: str | None
    detected_text: str | None
    confidence: float | None
    metadata: dict[str, Any]
    created_at: datetime
    #: Same as ``positions.job_id`` for this observation; ``None`` = legacy row.
    job_id: str | None = None


@dataclass
class NormalizedLabel:
    """One or more raw labels after merge evaluation. Traceability via raw_label_ids."""

    id: str
    inventory_id: str
    aisle_id: str
    position_id: str | None
    group_key: str
    canonical_sku: str | None
    canonical_product_name: str | None
    raw_label_ids: list[str]
    merge_rule_applied: str
    merge_confidence: float | None
    merge_reason: str
    review_required: bool
    metadata: dict[str, Any]
    created_at: datetime
    job_id: str | None = None


@dataclass
class FinalCountRecord:
    """Final business output: consolidated quantity per position/SKU."""

    id: str
    inventory_id: str
    aisle_id: str
    position_id: str | None
    sku: str | None
    product_name: str | None
    quantity: int
    normalized_label_ids: list[str]
    review_required: bool
    explanation_summary: str | None
    metadata: dict[str, Any]
    created_at: datetime
    job_id: str | None = None
