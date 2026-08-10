"""
In-memory implementation of SourceAssetRepository — v3.0 Épica 4.

list_by_aisle returns assets ordered by logical sequence when present, else uploaded_at ASC.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.errors import OrderedCaptureSessionConflictError, DuplicateUploadIdempotencyKeyError
from src.application.ports.repositories import SourceAssetRepository
from src.application.ports.rollup_contracts import AisleAssetRollup
from src.application.services.capture_sequence import sort_assets_by_logical_sequence
from src.domain.assets.entities import SourceAsset


class MemorySourceAssetRepository(SourceAssetRepository):
    def __init__(self) -> None:
        self._store: dict[str, SourceAsset] = {}

    def save(self, asset: SourceAsset) -> None:
        batch = (asset.upload_batch_id or "").strip()
        client = (asset.upload_client_file_id or "").strip()
        if batch and client:
            for existing in self._store.values():
                if existing.id == asset.id:
                    continue
                if (
                    existing.aisle_id == asset.aisle_id
                    and (existing.upload_batch_id or "").strip() == batch
                    and (existing.upload_client_file_id or "").strip() == client
                ):
                    raise DuplicateUploadIdempotencyKeyError(
                        "Duplicate upload idempotency key for this aisle "
                        f"(aisle_id={asset.aisle_id}, upload_batch_id={batch}, "
                        f"upload_client_file_id={client})"
                    )
        if asset.ordered_capture_session_id and asset.sequence_number is not None:
            for existing in self._store.values():
                if existing.id == asset.id:
                    continue
                if existing.ordered_capture_session_id != asset.ordered_capture_session_id:
                    continue
                if existing.sequence_number == asset.sequence_number and (
                    (existing.upload_client_file_id or "") != (asset.upload_client_file_id or "")
                ):
                    raise OrderedCaptureSessionConflictError(
                        "Duplicate ordered capture sequence",
                        code="ORDERED_CAPTURE_SEQUENCE_CONFLICT",
                    )
                if (
                    asset.upload_client_file_id
                    and (existing.upload_client_file_id or "") == asset.upload_client_file_id
                ):
                    raise OrderedCaptureSessionConflictError(
                        "Duplicate client_image_id in ordered capture session",
                        code="ORDERED_CAPTURE_CLIENT_IMAGE_CONFLICT",
                    )
        self._store[asset.id] = asset

    def get_by_id(self, asset_id: str) -> SourceAsset | None:
        return self._store.get(asset_id)

    def get_by_ids(self, asset_ids: Sequence[str]) -> dict[str, SourceAsset]:
        return {
            asset_id: self._store[asset_id]
            for asset_id in dict.fromkeys(asset_ids)
            if asset_id in self._store
        }

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

    def get_by_ordered_session_and_client_image_id(
        self,
        session_id: str,
        client_image_id: str,
    ) -> SourceAsset | None:
        sid = (session_id or "").strip()
        cid = (client_image_id or "").strip()
        if not sid or not cid:
            return None
        for a in self._store.values():
            if (
                (a.ordered_capture_session_id or "").strip() == sid
                and (a.upload_client_file_id or "").strip() == cid
            ):
                return a
        return None

    def get_by_ordered_session_and_sequence(
        self,
        session_id: str,
        sequence_number: int,
    ) -> SourceAsset | None:
        sid = (session_id or "").strip()
        if not sid:
            return None
        for a in self._store.values():
            if (
                (a.ordered_capture_session_id or "").strip() == sid
                and a.sequence_number == int(sequence_number)
            ):
                return a
        return None

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        assets = [a for a in self._store.values() if a.aisle_id == aisle_id]
        return sort_assets_by_logical_sequence(assets)

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
