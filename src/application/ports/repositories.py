"""
Repository ports — v3.0 (Documento técnico §9.1).

Use cases depend on these abstractions; infrastructure provides SQL (or other) implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from src.application.ports.contracts import PositionListQuery
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.evidence.entities import Evidence
from src.domain.inventory.entities import Inventory
from src.domain.jobs.entities import Job
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction


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
        ...


class SourceAssetRepository(ABC):
    @abstractmethod
    def save(self, asset: SourceAsset) -> None:
        ...

    @abstractmethod
    def get_by_id(self, asset_id: str) -> Optional[SourceAsset]:
        ...

    @abstractmethod
    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
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
    ) -> Sequence[Position]:
        """List positions for an aisle with optional filters and pagination (§9.7)."""
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
