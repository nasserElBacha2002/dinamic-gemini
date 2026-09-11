"""In-memory materialization receipt repository."""

from __future__ import annotations

from collections.abc import MutableMapping
from threading import RLock

from src.domain.position_materialization.entities import (
    PositionMaterializationAssociationReceipt,
)


class MemoryPositionMaterializationAssociationReceiptRepository:
    def __init__(
        self,
        *,
        store: MutableMapping[str, PositionMaterializationAssociationReceipt] | None = None,
        lock: RLock | None = None,
    ) -> None:
        self._store = store if store is not None else {}
        self._lock = lock or RLock()

    def save(self, receipt: PositionMaterializationAssociationReceipt) -> None:
        with self._lock:
            existing = self._store.get(receipt.request_id)
            if existing is not None and existing != receipt:
                raise ValueError("Materialization request already has a different receipt")
            if receipt.source_detection_id is not None and any(
                row.source_detection_id == receipt.source_detection_id
                and row.request_id != receipt.request_id
                for row in self._store.values()
            ):
                raise ValueError("Source detection already has a materialization receipt")
            self._store[receipt.request_id] = receipt

    def exists(self, request_id: str) -> bool:
        with self._lock:
            return request_id in self._store
