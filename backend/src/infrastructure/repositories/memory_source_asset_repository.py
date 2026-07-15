"""
In-memory implementation of SourceAssetRepository — v3.0 Épica 4.

list_by_aisle returns assets ordered by uploaded_at ASC to match SqlSourceAssetRepository.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import SourceAssetRepository
from src.application.ports.rollup_contracts import AisleAssetRollup
from src.domain.assets.entities import SourceAsset


class MemorySourceAssetRepository(SourceAssetRepository):
    def __init__(self) -> None:
        self._store: dict[str, SourceAsset] = {}

    def save(self, asset: SourceAsset) -> None:
        self._store[asset.id] = asset

    def get_by_id(self, asset_id: str) -> SourceAsset | None:
        return self._store.get(asset_id)

    def delete_by_id(self, asset_id: str) -> bool:
        if asset_id in self._store:
            del self._store[asset_id]
            return True
        return False

    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> SourceAsset | None:
        cid = (capture_session_item_id or "").strip()
        if not cid:
            return None
        for a in self._store.values():
            if (a.capture_session_item_id or "").strip() == cid:
                return a
        return None

    def get_by_upload_idempotency_key(
        self,
        aisle_id: str,
        upload_batch_id: str,
        upload_client_file_id: str,
    ) -> SourceAsset | None:
        aid = (aisle_id or "").strip()
        batch = (upload_batch_id or "").strip()
        client = (upload_client_file_id or "").strip()
        if not aid or not batch or not client:
            return None
        for a in self._store.values():
            if (
                a.aisle_id == aid
                and (a.upload_batch_id or "").strip() == batch
                and (a.upload_client_file_id or "").strip() == client
            ):
                return a
        return None

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        assets = [a for a in self._store.values() if a.aisle_id == aisle_id]
        return sorted(assets, key=lambda a: a.uploaded_at)

    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> dict[str, AisleAssetRollup]:
        if not aisle_ids:
            return {}
        wanted = set(aisle_ids)
        by_aisle: dict[str, list[SourceAsset]] = {aid: [] for aid in wanted}
        for a in self._store.values():
            if a.aisle_id in wanted:
                by_aisle.setdefault(a.aisle_id, []).append(a)
        out: dict[str, AisleAssetRollup] = {}
        for aid, assets in by_aisle.items():
            if not assets:
                continue
            last = max(a.uploaded_at for a in assets)
            out[aid] = AisleAssetRollup(count=len(assets), last_uploaded_at=last)
        return out
