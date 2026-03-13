"""
In-memory implementation of SourceAssetRepository — v3.0 Épica 4.

list_by_aisle returns assets ordered by uploaded_at ASC to match SqlSourceAssetRepository.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from src.application.ports.repositories import SourceAssetRepository
from src.domain.assets.entities import SourceAsset


class MemorySourceAssetRepository(SourceAssetRepository):
    def __init__(self) -> None:
        self._store: Dict[str, SourceAsset] = {}

    def save(self, asset: SourceAsset) -> None:
        self._store[asset.id] = asset

    def get_by_id(self, asset_id: str) -> Optional[SourceAsset]:
        return self._store.get(asset_id)

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        assets = [a for a in self._store.values() if a.aisle_id == aisle_id]
        return sorted(assets, key=lambda a: a.uploaded_at)
