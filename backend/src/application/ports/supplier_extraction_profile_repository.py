"""Port for SupplierExtractionProfile persistence (Phase 6)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.client_supplier.extraction_profile import (
    ReferenceAnnotation,
    SupplierExtractionProfile,
)


class SupplierExtractionProfileRepository(ABC):
    @abstractmethod
    def save(self, profile: SupplierExtractionProfile) -> None: ...

    @abstractmethod
    def get_by_id(self, profile_id: str) -> SupplierExtractionProfile | None: ...

    @abstractmethod
    def get_by_client_supplier_version(
        self, client_id: str, supplier_id: str, version: int
    ) -> SupplierExtractionProfile | None: ...

    @abstractmethod
    def get_active(
        self, client_id: str, supplier_id: str
    ) -> SupplierExtractionProfile | None: ...

    @abstractmethod
    def list_by_supplier(
        self, client_id: str, supplier_id: str
    ) -> Sequence[SupplierExtractionProfile]: ...

    @abstractmethod
    def next_version(self, client_id: str, supplier_id: str) -> int: ...

    @abstractmethod
    def create_next_version(
        self,
        *,
        client_id: str,
        supplier_id: str,
        profile_key: str,
        configuration: object,
        visual_notes: str | None,
        created_by: str | None,
        created_at: object,
        profile_id: str | None = None,
    ) -> SupplierExtractionProfile:
        """Atomically allocate next version and insert DRAFT (safe under concurrency)."""
        ...

    @abstractmethod
    def activate_version(
        self,
        *,
        client_id: str,
        supplier_id: str,
        profile_id: str,
        activated_by: str | None,
        expected_row_version: int | None = None,
    ) -> SupplierExtractionProfile:
        """Atomically supersede previous ACTIVE and activate target (SQL unique filter)."""
        ...


class SupplierReferenceAnnotationRepository(ABC):
    @abstractmethod
    def list_by_template(self, template_image_id: str) -> Sequence[ReferenceAnnotation]: ...

    @abstractmethod
    def replace_for_template(
        self, template_image_id: str, annotations: Sequence[ReferenceAnnotation]
    ) -> None: ...


__all__ = [
    "SupplierExtractionProfileRepository",
    "SupplierReferenceAnnotationRepository",
]
