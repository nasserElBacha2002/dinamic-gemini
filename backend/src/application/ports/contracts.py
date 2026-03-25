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

from src.application.ports.rollup_contracts import AisleAssetRollup
from src.domain.inventory.entities import Inventory
from src.domain.positions.entities import Position


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
    """Application row for GET /inventories (list): entity plus counts and ``last_activity_at``.

    ``last_activity_at`` is the maximum of inventory, aisle, and position ``created_at`` /
    ``updated_at`` — a list **freshness** signal, not a domain “last review completed” timestamp.
    """

    inventory: Inventory
    aisles_count: int
    pending_review_count: int
    last_activity_at: Optional[datetime]


@dataclass
class InventoryTableQuery:
    """Query for GET /api/v3/inventories table (search, filter, sort, pagination)."""

    search: Optional[str] = None
    """Case-insensitive substring on inventory name."""
    status: Optional[str] = None
    """Exact wire status match (e.g. draft, in_progress)."""
    sort_by: str = "created_at"
    """One of: name, created_at, updated_at, status, last_activity_at, pending_review_count, aisles_count."""
    sort_dir: str = "desc"
    """asc | desc"""
    page: int = 1
    page_size: int = 25


@dataclass
class AisleTableQuery:
    """Query for GET .../inventories/{id}/aisles table."""

    search: Optional[str] = None
    """Case-insensitive substring on aisle code."""
    status: Optional[str] = None
    sort_by: str = "code"
    """code | status | last_activity_at | pending_review_positions_count | positions_count | assets_count"""
    sort_dir: str = "asc"
    page: int = 1
    page_size: int = 25


@dataclass
class PositionListQuery:
    """Repository-level filters for raw positions before consolidation (§9.7).

    Pagination here limits **raw** rows fetched; list route applies **post-consolidation** page separately.
    """

    status: Optional[str] = None
    needs_review: Optional[bool] = None
    min_confidence: Optional[float] = None
    sku_filter: Optional[str] = None
    page: int = 1
    page_size: int = 25
    sort_by: str = "created_at"
    """SQL/order: created_at | updated_at | confidence | id"""
    sort_dir: str = "asc"


@dataclass(frozen=True)
class ReviewQueueQuery:
    """Cross-inventory review queue list."""

    inventory_id: Optional[str] = None
    aisle_id: Optional[str] = None
    min_confidence: Optional[float] = None
    sort_by: str = "updated_at"
    """updated_at | created_at | confidence"""
    sort_dir: str = "desc"
    page: int = 1
    page_size: int = 25


@dataclass(frozen=True)
class ReviewQueueListRow:
    """One row for GET /api/v3/review-queue/positions (position + navigation context)."""

    position: Position
    inventory_id: str
    inventory_name: str
    aisle_code: str
