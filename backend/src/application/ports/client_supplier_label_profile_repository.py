"""Port for ClientSupplier label profile source configuration (Phase 1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.label_profiles.entities import ClientSupplierLabelProfile
from src.domain.label_profiles.kinds import LabelKind


class ClientSupplierLabelProfileRepository(ABC):
    @abstractmethod
    def upsert(self, profile: ClientSupplierLabelProfile) -> ClientSupplierLabelProfile: ...

    @abstractmethod
    def get_by_supplier_and_kind(
        self, client_supplier_id: str, label_kind: LabelKind
    ) -> ClientSupplierLabelProfile | None: ...

    @abstractmethod
    def list_by_supplier(
        self, client_supplier_id: str
    ) -> Sequence[ClientSupplierLabelProfile]: ...

    @abstractmethod
    def delete_by_supplier_and_kind(
        self, client_supplier_id: str, label_kind: LabelKind
    ) -> None: ...
