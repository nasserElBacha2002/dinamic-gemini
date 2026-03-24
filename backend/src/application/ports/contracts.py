"""
Typed contracts for application ports — v3.0.

Lightweight TypedDict/dataclass structures for analysis result, mapped positions,
metrics, queue payloads, and position list query. Reduces reliance on Dict[str, Any].
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict

from src.domain.inventory.entities import Inventory


# --- Analysis (AnalysisProvider.analyze_aisle) ---


class ProductItemPayload(TypedDict, total=False):
    """Single product inside a position (pipeline output §9.4)."""
    sku: str
    description: str
    quantity: int
    confidence: float


class MappedPositionPayload(TypedDict, total=False):
    """One position in pipeline output (§9.4). Used by ResultMapper."""
    id: str
    confidence: float
    needs_review: bool
    primary_evidence_id: Optional[str]
    products: List[ProductItemPayload]
    detected_summary_json: Optional[Dict[str, Any]]
    review_reason: Optional[str]


class AnalysisResultPayload(TypedDict, total=False):
    """Result of AnalysisProvider.analyze_aisle (§9.4)."""
    positions: List[MappedPositionPayload]
    aisle_id: str


# --- Metrics (MetricsCalculator) ---


class InventoryMetricsResult(TypedDict, total=False):
    """Return type of MetricsCalculator.calculate_inventory_metrics (§9.6).
    Implementations must return all keys so the API layer can serialize without validation errors."""
    total_reviewed_positions: int
    total_positions: int
    auto_accepted_positions: int
    corrected_positions: int
    deleted_positions: int
    success_rate: float
    correction_rate: float
    deletion_rate: float


# --- Queue (JobQueue.enqueue payload) ---


class ProcessAislePayload(TypedDict):
    """Payload for process_aisle job type."""
    aisle_id: str


# --- Position list query (PositionRepository) ---


@dataclass(frozen=True)
class InventoryListItem:
    """One inventory row for list/summary screens: entity plus aggregates for tables and cards."""

    inventory: Inventory
    aisles_count: int
    pending_review_count: int
    last_activity_at: Optional[datetime]


@dataclass
class PositionListQuery:
    """Optional filters and pagination for listing positions by aisle (§9.7)."""
    status: Optional[str] = None
    needs_review: Optional[bool] = None
    min_confidence: Optional[float] = None
    sku_filter: Optional[str] = None
    page: int = 1
    page_size: int = 25
