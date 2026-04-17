"""
Repository ports — v3.0 (Documento técnico §9.1).

Use cases depend on these abstractions; infrastructure provides SQL (or other) implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Literal, Optional, Sequence, Union

from src.application.ports.contracts import PositionListQuery
from src.application.ports.rollup_contracts import AisleAssetRollup
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.evidence.entities import Evidence
from src.domain.inventory.entities import Inventory
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.domain.jobs.entities import Job
from src.domain.labels.entities import FinalCountRecord, NormalizedLabel, RawLabel
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction


class _JobIdFilterUnset:
    """Pass as ``job_id`` to ``list_by_aisle`` to omit a ``job_id`` predicate (all rows for aisle)."""


JOB_ID_FILTER_UNSET = _JobIdFilterUnset()

LabelJobScope = Union[str, Literal["all"], None]
"""``job_id`` filter for label/count repositories: ``\"all\"`` = no filter; ``None`` = ``IS NULL``; else equality."""


class InventoryRepository(ABC):
    @abstractmethod
    def save(self, inventory: Inventory) -> None:
        ...

    @abstractmethod
    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        ...

    @abstractmethod
    def list_all(self) -> Sequence[Inventory]:
        """Return all inventories. Order is implementation-defined (SQL impl: created_at DESC)."""
        ...


class AisleRepository(ABC):
    @abstractmethod
    def save(self, aisle: Aisle) -> None:
        ...

    @abstractmethod
    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        ...

    @abstractmethod
    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        """Return aisles for the given inventory. Order is implementation-defined (SQL impl: created_at DESC)."""
        ...

    @abstractmethod
    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        """Return the aisle with the given code in the given inventory, or None. Used for duplicate checks."""
        ...


class SourceAssetRepository(ABC):
    @abstractmethod
    def save(self, asset: SourceAsset) -> None:
        ...

    @abstractmethod
    def get_by_id(self, asset_id: str) -> Optional[SourceAsset]:
        ...

    @abstractmethod
    def delete_by_id(self, asset_id: str) -> bool:
        """Delete the row by primary key. Returns True if a row was removed."""

    @abstractmethod
    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        ...

    @abstractmethod
    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> Dict[str, AisleAssetRollup]:
        """Return upload count and latest ``uploaded_at`` per aisle id (missing aisles omitted or zero)."""
        ...


class PositionRepository(ABC):
    @abstractmethod
    def save(self, position: Position) -> None:
        ...

    @abstractmethod
    def get_by_id(self, position_id: str) -> Optional[Position]:
        ...

    @abstractmethod
    def list_by_aisle(
        self,
        aisle_id: str,
        status: Optional[str] = None,
        needs_review: Optional[bool] = None,
        min_confidence: Optional[float] = None,
        sku_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
        job_id: Union[str, None, _JobIdFilterUnset] = JOB_ID_FILTER_UNSET,
    ) -> Sequence[Position]:
        """List positions for an aisle with optional filters and pagination (§9.7).
        sku_filter: when set, only positions that have at least one product_record with
        sku containing this string (substring match) are returned. In-memory impl may ignore it.
        job_id: ``JOB_ID_FILTER_UNSET`` (default) = all positions in the aisle (every run slice);
        ``None`` = legacy ``job_id IS NULL``; ``str`` = that inventory job only. Phase 1 callers that
        need one run must pass a concrete ``job_id``."""
        ...

    @abstractmethod
    def list_by_aisle_query(
        self, aisle_id: str, query: Optional[PositionListQuery] = None
    ) -> Sequence[Position]:
        """List positions for an aisle using optional PositionListQuery. Default query implies page=1, page_size=25."""
        ...

    @abstractmethod
    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        """List positions for multiple aisles (e.g. for metrics)."""
        ...


class ProductRecordRepository(ABC):
    @abstractmethod
    def save(self, product: ProductRecord) -> None:
        ...

    @abstractmethod
    def get_by_id(self, product_id: str) -> Optional[ProductRecord]:
        ...

    @abstractmethod
    def list_by_position(self, position_id: str) -> Sequence[ProductRecord]:
        ...

    def list_by_position_ids(self, position_ids: Sequence[str]) -> Sequence[ProductRecord]:
        """Product rows for any ``position_id`` in ``position_ids`` (empty → empty).

        Default: one ``list_by_position`` per **distinct** id (legacy-compatible). SQL/memory
        implementations override with a single batch query / scan.
        """
        if not position_ids:
            return []
        out: List[ProductRecord] = []
        for pid in dict.fromkeys(position_ids):
            out.extend(self.list_by_position(pid))
        return out


class EvidenceRepository(ABC):
    @abstractmethod
    def save(self, evidence: Evidence) -> None:
        ...

    @abstractmethod
    def get_by_id(self, evidence_id: str) -> Optional[Evidence]:
        ...

    @abstractmethod
    def list_by_entity(self, entity_type: str, entity_id: str) -> Sequence[Evidence]:
        ...


class ReviewActionRepository(ABC):
    @abstractmethod
    def save(self, review: ReviewAction) -> None:
        ...

    @abstractmethod
    def list_by_position(self, position_id: str) -> Sequence[ReviewAction]:
        ...


class JobRepository(ABC):
    @abstractmethod
    def save(self, job: Job) -> None:
        ...

    @abstractmethod
    def get_by_id(self, job_id: str) -> Optional[Job]:
        ...

    @abstractmethod
    def get_latest_by_target(self, target_type: str, target_id: str) -> Optional[Job]:
        """Return the most recently updated (or created) job for the given target, or None."""
        ...

    @abstractmethod
    def get_latest_by_targets(
        self, target_type: str, target_ids: Sequence[str]
    ) -> Dict[str, Job]:
        """Return the latest job per target_id for the given target_type. Keys are target_id; only one job per target (the latest by updated_at, then created_at). Missing targets are omitted from the dict."""
        ...

    @abstractmethod
    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        """Jobs for one target, newest first (``updated_at DESC``, ``created_at DESC``)."""

    def list_all_jobs(self) -> Sequence[Job]:
        """Bulk read for analytics. Default empty; SQL/memory implementations scan ``inventory_jobs``."""
        return []


# --- v3.2.3 Label consolidation layers ---


class RawLabelRepository(ABC):
    """Persist and read raw labels (original observations)."""

    @abstractmethod
    def save_many(self, labels: List[RawLabel]) -> None:
        ...

    @abstractmethod
    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[RawLabel]:
        """Raw labels for scope. ``job_id=\"all\"`` = no filter; ``None`` = legacy null; else one job."""
        ...


class NormalizedLabelRepository(ABC):
    """Persist and read normalized labels (after merge)."""

    @abstractmethod
    def save_many(self, labels: List[NormalizedLabel]) -> None:
        ...

    @abstractmethod
    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[NormalizedLabel]:
        ...

    @abstractmethod
    def replace_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> None:
        """Remove normalized labels for scope slice; caller then saves new ones. Idempotent recompute."""
        ...


class FinalCountRepository(ABC):
    """Persist and read final count records (business output)."""

    @abstractmethod
    def save_many(self, records: List[FinalCountRecord]) -> None:
        ...

    @abstractmethod
    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[FinalCountRecord]:
        ...

    @abstractmethod
    def list_by_position(self, position_id: str) -> Sequence[FinalCountRecord]:
        """Final count records for one position (e.g. to apply to ProductRecord)."""

    @abstractmethod
    def replace_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> None:
        """Remove final count rows for scope slice; caller then saves new ones."""
        ...


class InventoryVisualReferenceRepository(ABC):
    """Persist and list visual reference images per inventory (v3.2.4).

    list_by_inventory must return references ordered by created_at ASC, id ASC.
    """

    @abstractmethod
    def get_by_id(self, reference_id: str) -> Optional[InventoryVisualReference]:
        """Return one reference by id, or None when it does not exist."""
        ...

    @abstractmethod
    def create(self, reference: InventoryVisualReference) -> None:
        """Insert a new reference. Must fail if the id already exists."""
        ...

    @abstractmethod
    def create_many(self, references: Sequence[InventoryVisualReference]) -> None:
        """Insert references atomically if supported by the implementation.

        Must fail if any id already exists. Implementations should avoid partial writes.
        """
        ...

    @abstractmethod
    def list_by_inventory(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        """Return all visual references for the given inventory ordered by created_at ASC, id ASC."""
        ...

    @abstractmethod
    def update(self, reference: InventoryVisualReference) -> None:
        """Update an existing reference in place. Must fail when the id does not exist."""
        ...

    @abstractmethod
    def delete(self, reference_id: str) -> None:
        """Delete one reference by id. Should be idempotent for storage cleanup callers."""
        ...
