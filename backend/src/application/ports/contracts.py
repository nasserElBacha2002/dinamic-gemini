"""
Typed contracts for application ports — v3.0.

Lightweight TypedDict/dataclass structures for analysis result, mapped positions,
metrics, queue payloads, and position list query. Reduces reliance on Dict[str, Any].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from typing_extensions import TypedDict

from src.application.ports.rollup_contracts import AisleAssetRollup  # noqa: F401 — public re-export
from src.domain.inventory.entities import Inventory
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord

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
    primary_evidence_id: str | None
    products: list[ProductItemPayload]
    detected_summary_json: dict[str, Any] | None
    review_reason: str | None


class AnalysisResultPayload(TypedDict, total=False):
    """Result of AnalysisProvider.analyze_aisle (§9.4)."""

    positions: list[MappedPositionPayload]
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
    last_activity_at: datetime | None


@dataclass
class InventoryTableQuery:
    """Query for GET /api/v3/inventories table (search, filter, sort, pagination)."""

    search: str | None = None
    """Case-insensitive substring on inventory name."""
    status: str | None = None
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

    search: str | None = None
    """Case-insensitive substring on aisle code."""
    status: str | None = None
    sort_by: str = "code"
    """code | status | last_activity_at | pending_review_positions_count | positions_count | assets_count"""
    sort_dir: str = "asc"
    page: int = 1
    page_size: int = 25


class _PositionListJobIdUnset:
    """Sentinel: omit job_id predicate (all slices). Phase 2 list/detail pass a resolved slice."""


POSITION_LIST_JOB_ID_UNSET = _PositionListJobIdUnset()


@dataclass
class PositionListQuery:
    """Repository-level filters for raw positions before consolidation (§9.7).

    Pagination here limits **raw** rows fetched; list route applies **post-consolidation** page separately.
    """

    status: str | None = None
    needs_review: bool | None = None
    min_confidence: float | None = None
    sku_filter: str | None = None
    page: int = 1
    page_size: int = 25
    sort_by: str = "created_at"
    """SQL/order: created_at | updated_at | confidence | id"""
    sort_dir: str = "asc"
    job_id: str | None | _PositionListJobIdUnset = field(
        default_factory=lambda: POSITION_LIST_JOB_ID_UNSET
    )
    """Unset = no job filter; ``None`` = legacy null job_id rows; ``str`` = one inventory job."""


@dataclass(frozen=True)
class ReviewQueueQuery:
    """Cross-inventory review queue list (Sprint 4.2 — filters + priority sort)."""

    inventory_id: str | None = None
    aisle_id: str | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None
    traceability: str | None = None
    """API traceability wire value: valid | missing | invalid | unvalidated."""
    has_evidence: bool | None = None
    qty_zero: bool | None = None
    sku_contains: str | None = None
    position_status: str | None = None
    """detected | reviewed | corrected | deleted | confirmed (reviewed or corrected)."""
    sort_by: str = "priority"
    """priority | updated_at | created_at | confidence"""
    sort_dir: str = "desc"
    page: int = 1
    page_size: int = 25


@dataclass(frozen=True)
class ReviewQueueSummary:
    """KPI counts for the filtered queue population (full result set before pagination)."""

    pending_review: int
    low_confidence: int
    invalid_traceability: int
    qty_zero: int
    missing_evidence: int


@dataclass(frozen=True)
class ReviewQueueListRow:
    """One row for GET /api/v3/review-queue/positions (position + navigation context)."""

    position: Position
    inventory_id: str
    inventory_name: str
    aisle_code: str
    #: Display-primary product for this position (same rule as review queue filters/sort).
    primary_product: ProductRecord | None = None
