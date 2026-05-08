"""
Repository ports — v3.0 (Documento técnico §9.1).

Use cases depend on these abstractions; infrastructure provides SQL (or other) implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Literal, Union

from src.application.ports.contracts import PositionListQuery
from src.application.ports.rollup_contracts import AisleAssetRollup
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.client.entities import Client
from src.domain.client_supplier.entities import ClientSupplier
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.domain.client_supplier.reference_image import SupplierReferenceImage
from src.domain.evidence.entities import Evidence
from src.domain.inventory.entities import Inventory
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
    def save(self, inventory: Inventory) -> None: ...

    @abstractmethod
    def get_by_id(self, inventory_id: str) -> Inventory | None: ...

    @abstractmethod
    def list_all(self) -> Sequence[Inventory]:
        """Return all inventories. Order is implementation-defined (SQL impl: created_at DESC)."""
        ...


class ClientRepository(ABC):
    @abstractmethod
    def save(self, client: Client) -> None: ...

    @abstractmethod
    def get_by_id(self, client_id: str) -> Client | None: ...

    @abstractmethod
    def list_all(self) -> Sequence[Client]:
        """Return all clients. Order is implementation-defined (SQL impl: created_at DESC)."""
        ...


class ClientSupplierRepository(ABC):
    @abstractmethod
    def save(self, supplier: ClientSupplier) -> None: ...

    @abstractmethod
    def get_by_id(self, supplier_id: str) -> ClientSupplier | None: ...

    @abstractmethod
    def get_by_client_and_name(self, client_id: str, name: str) -> ClientSupplier | None: ...

    @abstractmethod
    def list_by_client(self, client_id: str) -> Sequence[ClientSupplier]:
        """Return suppliers for one client. Order is implementation-defined (SQL impl: created_at DESC)."""
        ...


class AisleRepository(ABC):
    @abstractmethod
    def save(self, aisle: Aisle) -> None: ...

    @abstractmethod
    def get_by_id(self, aisle_id: str) -> Aisle | None: ...

    @abstractmethod
    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        """Return aisles for the given inventory. Order is implementation-defined (SQL impl: created_at DESC)."""
        ...

    @abstractmethod
    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        """Return the aisle with the given code in the given inventory, or None. Used for duplicate checks."""
        ...


class SourceAssetRepository(ABC):
    @abstractmethod
    def save(self, asset: SourceAsset) -> None: ...

    @abstractmethod
    def get_by_id(self, asset_id: str) -> SourceAsset | None: ...

    @abstractmethod
    def delete_by_id(self, asset_id: str) -> bool:
        """Delete the row by primary key. Returns True if a row was removed."""

    @abstractmethod
    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]: ...

    @abstractmethod
    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> dict[str, AisleAssetRollup]:
        """Return upload count and latest ``uploaded_at`` per aisle id (missing aisles omitted or zero)."""
        ...

    @abstractmethod
    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> SourceAsset | None:
        """Return the asset linked to this capture item id, if any (G5 idempotency)."""
        ...


class PositionRepository(ABC):
    @abstractmethod
    def save(self, position: Position) -> None: ...

    @abstractmethod
    def get_by_id(self, position_id: str) -> Position | None: ...

    @abstractmethod
    def list_by_aisle(
        self,
        aisle_id: str,
        status: str | None = None,
        needs_review: bool | None = None,
        min_confidence: float | None = None,
        sku_filter: str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
        job_id: str | None | _JobIdFilterUnset = JOB_ID_FILTER_UNSET,
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
        self, aisle_id: str, query: PositionListQuery | None = None
    ) -> Sequence[Position]:
        """List positions for an aisle using optional PositionListQuery. Default query implies page=1, page_size=25."""
        ...

    @abstractmethod
    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        """List positions for multiple aisles (e.g. for metrics)."""
        ...


class ProductRecordRepository(ABC):
    @abstractmethod
    def save(self, product: ProductRecord) -> None: ...

    @abstractmethod
    def get_by_id(self, product_id: str) -> ProductRecord | None: ...

    @abstractmethod
    def list_by_position(self, position_id: str) -> Sequence[ProductRecord]: ...

    def list_by_position_ids(self, position_ids: Sequence[str]) -> Sequence[ProductRecord]:
        """Product rows for any ``position_id`` in ``position_ids`` (empty → empty).

        Default: one ``list_by_position`` per **distinct** id (legacy-compatible). SQL/memory
        implementations override with a single batch query / scan.
        """
        if not position_ids:
            return []
        out: list[ProductRecord] = []
        for pid in dict.fromkeys(position_ids):
            out.extend(self.list_by_position(pid))
        return out


class EvidenceRepository(ABC):
    @abstractmethod
    def save(self, evidence: Evidence) -> None: ...

    @abstractmethod
    def get_by_id(self, evidence_id: str) -> Evidence | None: ...

    @abstractmethod
    def list_by_entity(self, entity_type: str, entity_id: str) -> Sequence[Evidence]: ...


class ReviewActionRepository(ABC):
    @abstractmethod
    def save(self, review: ReviewAction) -> None: ...

    @abstractmethod
    def list_by_position(self, position_id: str) -> Sequence[ReviewAction]: ...


class JobRepository(ABC):
    @abstractmethod
    def save(self, job: Job) -> None: ...

    @abstractmethod
    def get_by_id(self, job_id: str) -> Job | None: ...

    @abstractmethod
    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        """Return the most recently updated (or created) job for the given target, or None."""
        ...

    @abstractmethod
    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> dict[str, Job]:
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
    def save_many(self, labels: list[RawLabel]) -> None: ...

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
    def save_many(self, labels: list[NormalizedLabel]) -> None: ...

    @abstractmethod
    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[NormalizedLabel]: ...

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
    def save_many(self, records: list[FinalCountRecord]) -> None: ...

    @abstractmethod
    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[FinalCountRecord]: ...

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


class SupplierReferenceImageRepository(ABC):
    """Persist and list reference images per supplier (Phase C1)."""

    @abstractmethod
    def get_by_id(self, reference_image_id: str) -> SupplierReferenceImage | None:
        """Return one supplier reference image by id, or None when it does not exist."""
        ...

    @abstractmethod
    def create(self, reference_image: SupplierReferenceImage) -> None:
        """Insert one supplier reference image. Must fail if the id already exists."""
        ...

    @abstractmethod
    def create_many(self, reference_images: Sequence[SupplierReferenceImage]) -> None:
        """Insert images atomically if supported. Must fail if any id already exists."""
        ...

    @abstractmethod
    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierReferenceImage]:
        """Return supplier reference images ordered by created_at ASC, id ASC."""
        ...

    @abstractmethod
    def delete(self, reference_image_id: str) -> None:
        """Delete one supplier reference image by id. Idempotent for storage cleanup callers."""
        ...


class SupplierPromptConfigRepository(ABC):
    """Persist and query supplier prompt configurations (Phase D2)."""

    @abstractmethod
    def create(self, config: SupplierPromptConfig) -> SupplierPromptConfig:
        """Insert one supplier prompt config row and return the stored entity."""
        ...

    @abstractmethod
    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierPromptConfig]:
        """Return configs ordered deterministically by provider/scope/version recency."""
        ...

    @abstractmethod
    def list_versions_by_scope(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> Sequence[SupplierPromptConfig]:
        """Return versions for one supplier/provider/model scope (newest first)."""
        ...

    @abstractmethod
    def get_by_id(self, config_id: str) -> SupplierPromptConfig | None:
        """Return one config by id, or None."""
        ...

    @abstractmethod
    def get_active_by_scope(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> SupplierPromptConfig | None:
        """Return active config for exact scope, or None."""
        ...

    @abstractmethod
    def get_latest_version_number(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> int | None:
        """Return max version for exact scope, or None when no rows exist."""
        ...

    @abstractmethod
    def deactivate_scope(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> None:
        """Set is_active=0 for all rows in exact scope."""
        ...

    @abstractmethod
    def activate_version(self, config_id: str) -> SupplierPromptConfig | None:
        """Set one version active (and other scope rows inactive), returning the activated row."""
        ...
