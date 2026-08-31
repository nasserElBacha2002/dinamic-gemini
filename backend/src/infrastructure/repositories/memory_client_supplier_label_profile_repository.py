"""In-memory ClientSupplierLabelProfile repository (Phase 1)."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.client_supplier_label_profile_repository import (
    ClientSupplierLabelProfileRepository,
)
from src.domain.label_profiles.entities import ClientSupplierLabelProfile
from src.domain.label_profiles.kinds import LabelKind


class MemoryClientSupplierLabelProfileRepository(ClientSupplierLabelProfileRepository):
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, LabelKind], ClientSupplierLabelProfile] = {}

    def upsert(self, profile: ClientSupplierLabelProfile) -> ClientSupplierLabelProfile:
        key = (profile.client_supplier_id, profile.label_kind)
        self._by_key[key] = profile
        return profile

    def get_by_supplier_and_kind(
        self, client_supplier_id: str, label_kind: LabelKind
    ) -> ClientSupplierLabelProfile | None:
        return self._by_key.get((client_supplier_id, label_kind))

    def list_by_supplier(
        self, client_supplier_id: str
    ) -> Sequence[ClientSupplierLabelProfile]:
        out = [p for p in self._by_key.values() if p.client_supplier_id == client_supplier_id]
        out.sort(key=lambda p: p.label_kind.value)
        return out

    def delete_by_supplier_and_kind(
        self, client_supplier_id: str, label_kind: LabelKind
    ) -> None:
        self._by_key.pop((client_supplier_id, label_kind), None)
