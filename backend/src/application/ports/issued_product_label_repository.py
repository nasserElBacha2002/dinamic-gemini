"""Issued physical product labels (print/mint registry — global unique label_id)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class IssuedProductLabel:
    id: str
    client_id: str
    label_id: str
    internal_code: str
    quantity: int
    format_version: str
    checksum: str
    payload: str
    created_at: datetime
    created_by: str | None = None


class IssuedProductLabelRepository(Protocol):
    def save(self, row: IssuedProductLabel) -> None:
        """Insert. Raise on unique label_id collision (caller retries with new id)."""
        ...

    def get_by_label_id(self, label_id: str) -> IssuedProductLabel | None: ...

    def list_by_client(
        self, client_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[IssuedProductLabel]: ...
