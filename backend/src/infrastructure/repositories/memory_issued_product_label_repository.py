"""In-memory issued product labels (tests / local)."""

from __future__ import annotations

from src.application.ports.issued_product_label_repository import (
    IssuedProductLabel,
    IssuedProductLabelRepository,
)


class MemoryIssuedProductLabelRepository(IssuedProductLabelRepository):
    def __init__(self) -> None:
        self._by_label: dict[str, IssuedProductLabel] = {}
        self._order: list[str] = []

    def save(self, row: IssuedProductLabel) -> None:
        key = row.label_id.upper()
        if key in self._by_label:
            raise ValueError(f"duplicate label_id: {key}")
        self._by_label[key] = row
        self._order.append(key)

    def get_by_label_id(self, label_id: str) -> IssuedProductLabel | None:
        return self._by_label.get(label_id.upper())

    def list_by_client(
        self, client_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[IssuedProductLabel]:
        rows = [self._by_label[k] for k in self._order if self._by_label[k].client_id == client_id]
        rows.reverse()  # newest last-inserted first among client
        return rows[offset : offset + limit]
