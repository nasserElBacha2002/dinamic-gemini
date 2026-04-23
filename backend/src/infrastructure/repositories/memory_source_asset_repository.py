"""
In-memory implementation of SourceAssetRepository — v3.0 Épica 4.

list_by_aisle returns assets ordered by uploaded_at ASC to match SqlSourceAssetRepository.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from src.application.ports.rollup_contracts import AisleAssetRollup
from src.application.ports.repositories import SourceAssetRepository
from src.domain.assets.entities import SourceAsset


class MemorySourceAssetRepository(SourceAssetRepository):
    def __init__(self) -> None:
        self._store: Dict[str, SourceAsset] = {}

    def save(self, asset: SourceAsset) -> None:
        self._store[asset.id] = asset

    def get_by_id(self, asset_id: str) -> Optional[SourceAsset]:
        return self._store.get(asset_id)

    def delete_by_id(self, asset_id: str) -> bool:
        if asset_id in self._store:
            del self._store[asset_id]
            return True
        return False

    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> Optional[SourceAsset]:
        cid = (capture_session_item_id or "").strip()
        if not cid:
            return None
        for a in self._store.values():
            if (a.capture_session_item_id or "").strip() == cid:
                return a
        return None

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        assets = [a for a in self._store.values() if a.aisle_id == aisle_id]
        return sorted(assets, key=lambda a: a.uploaded_at)

    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> Dict[str, AisleAssetRollup]:
        if not aisle_ids:
            return {}
        wanted = set(aisle_ids)
        by_aisle: Dict[str, list[SourceAsset]] = {aid: [] for aid in wanted}
        for a in self._store.values():
            if a.aisle_id in wanted:
                by_aisle.setdefault(a.aisle_id, []).append(a)
        out: Dict[str, AisleAssetRollup] = {}
        for aid, assets in by_aisle.items():
            if not assets:
                continue
            last = max(a.uploaded_at for a in assets)
            out[aid] = AisleAssetRollup(count=len(assets), last_uploaded_at=last)
        return out
