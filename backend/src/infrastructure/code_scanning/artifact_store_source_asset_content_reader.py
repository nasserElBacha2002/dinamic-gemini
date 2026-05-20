"""Load source asset bytes via ArtifactStore (S3/local)."""

from __future__ import annotations

import logging

from src.domain.assets.entities import SourceAsset
from src.infrastructure.storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


class ArtifactStoreSourceAssetContentReader:
    def __init__(self, artifact_store: ArtifactStore) -> None:
        self._store = artifact_store

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        key = (asset.storage_key or "").strip()
        if not key:
            raise ValueError(f"Source asset {asset.id} has no storage_key")
        try:
            downloaded = self._store.get_object(key)
        except Exception as exc:
            logger.warning(
                "code_scan storage_read_failed asset_id=%s storage_key=%s error=%s",
                asset.id,
                key,
                type(exc).__name__,
            )
            raise FileNotFoundError(f"Storage object not found for asset {asset.id}") from exc
        content = downloaded.content
        if not content:
            raise ValueError(f"Empty storage object for asset {asset.id}")
        return content
