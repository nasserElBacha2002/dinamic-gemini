"""Mixins so Client/ClientSupplier test stubs satisfy abstract batch port methods."""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.client.entities import Client
from src.domain.client_supplier.entities import ClientSupplier


class ClientRepositoryBatchMixin:
    """Implements ``get_by_ids`` via ``get_by_id`` for in-memory stubs only."""

    def get_by_ids(self, client_ids: Sequence[str]) -> dict[str, Client]:
        out: dict[str, Client] = {}
        for client_id in {cid for cid in client_ids if cid}:
            row = self.get_by_id(client_id)  # type: ignore[attr-defined]
            if row is not None:
                out[client_id] = row
        return out


class ClientSupplierRepositoryBatchMixin:
    """Implements batch supplier lookups via ``get_by_id`` for in-memory stubs only."""

    def get_by_ids(self, supplier_ids: Sequence[str]) -> dict[str, ClientSupplier]:
        out: dict[str, ClientSupplier] = {}
        for supplier_id in {sid for sid in supplier_ids if sid}:
            row = self.get_by_id(supplier_id)  # type: ignore[attr-defined]
            if row is not None:
                out[supplier_id] = row
        return out

    def get_by_client_and_ids(
        self, client_id: str, supplier_ids: Sequence[str]
    ) -> dict[str, ClientSupplier]:
        out: dict[str, ClientSupplier] = {}
        if not client_id:
            return out
        for supplier_id in {sid for sid in supplier_ids if sid}:
            row = self.get_by_id(supplier_id)  # type: ignore[attr-defined]
            if row is not None and row.client_id == client_id:
                out[supplier_id] = row
        return out
