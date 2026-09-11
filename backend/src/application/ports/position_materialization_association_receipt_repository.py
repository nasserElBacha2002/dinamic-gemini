"""Durable downstream-evidence receipts for position materialization."""

from __future__ import annotations

from typing import Protocol

from src.domain.position_materialization.entities import (
    PositionMaterializationAssociationReceipt,
)


class PositionMaterializationAssociationReceiptRepository(Protocol):
    def save(self, receipt: PositionMaterializationAssociationReceipt) -> None: ...

    def exists(self, request_id: str) -> bool: ...
