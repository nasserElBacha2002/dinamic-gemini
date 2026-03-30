from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.domain.assets.entities import SourceAsset
from src.domain.inventory.visual_reference import InventoryVisualReference

logger = logging.getLogger(__name__)


class WorkerInputArtifactResolver:
    """Resolve durable artifact metadata into temporary local files for worker execution."""

    def __init__(self, artifact_store, *, legacy_base: Path, legacy_local_read_enabled: bool) -> None:
        self._artifact_store = artifact_store
        self._legacy_base = legacy_base.resolve()
        self._legacy_local_read_enabled = bool(legacy_local_read_enabled)

    def _safe_legacy_path(self, rel_path: str) -> Path:
        raw = (rel_path or "").strip()
        if not raw:
            raise RuntimeError("legacy storage_path is empty")
        full = (self._legacy_base / raw).resolve()
        try:
            full.relative_to(self._legacy_base)
        except ValueError as exc:
            raise RuntimeError(f"legacy storage_path escapes base dir: {raw}") from exc
        return full

    def _download_provider_key(self, *, provider: str, key: str, target_path: Path, label: str) -> Path:
        if self._artifact_store is None or not hasattr(self._artifact_store, "get_object"):
            raise RuntimeError(
                f"{label}: storage_provider={provider} storage_key={key} but artifact store is unavailable"
            )
        logger.info(
            "%s source selected provider=%s storage_key=%s target=%s",
            label,
            provider,
            key,
            str(target_path),
        )
        try:
            obj = self._artifact_store.get_object(key)
        except Exception as exc:
            raise RuntimeError(
                f"{label}: failed to download provider object provider={provider} storage_key={key}"
            ) from exc
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(obj.content)
        logger.info(
            "%s source resolved provider=%s storage_key=%s target=%s bytes=%s",
            label,
            provider,
            key,
            str(target_path),
            len(obj.content),
        )
        return target_path

    def resolve_source_asset(self, asset: SourceAsset, target_path: Path) -> Path:
        provider = (asset.storage_provider or "").strip().lower()
        key = (asset.storage_key or "").strip()
        if provider or key:
            if not provider:
                raise RuntimeError(f"source asset {asset.id}: storage_key is set but storage_provider is missing")
            if not key:
                raise RuntimeError(f"source asset {asset.id}: storage_provider={provider} but storage_key is missing")
            return self._download_provider_key(
                provider=provider,
                key=key,
                target_path=target_path,
                label=f"source asset {asset.id}",
            )
        if not self._legacy_local_read_enabled:
            raise RuntimeError(
                f"source asset {asset.id}: provider metadata absent and legacy local fallback is disabled"
            )
        src = self._safe_legacy_path(asset.storage_path)
        if not src.exists():
            raise RuntimeError(f"source asset {asset.id}: legacy file not found at {src}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(src.read_bytes())
        logger.info(
            "source asset %s source selected provider=legacy_local storage_path=%s target=%s",
            asset.id,
            asset.storage_path,
            str(target_path),
        )
        return target_path

    def resolve_visual_reference(
        self,
        reference_id: str,
        *,
        reference_record: Optional[InventoryVisualReference],
        source_path: str,
        target_path: Path,
    ) -> Path:
        provider = (getattr(reference_record, "storage_provider", None) or "").strip().lower()
        key = (getattr(reference_record, "storage_key", None) or "").strip()
        if provider or key:
            if not provider:
                raise RuntimeError(
                    f"visual reference {reference_id}: storage_key is set but storage_provider is missing"
                )
            if not key:
                raise RuntimeError(
                    f"visual reference {reference_id}: storage_provider={provider} but storage_key is missing"
                )
            return self._download_provider_key(
                provider=provider,
                key=key,
                target_path=target_path,
                label=f"visual reference {reference_id}",
            )
        if not self._legacy_local_read_enabled:
            raise RuntimeError(
                f"visual reference {reference_id}: provider metadata absent and legacy local fallback is disabled"
            )
        src = self._safe_legacy_path(source_path)
        if not src.exists():
            raise RuntimeError(f"visual reference {reference_id}: legacy file not found at {src}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(src.read_bytes())
        logger.info(
            "visual reference %s source selected provider=legacy_local storage_path=%s target=%s",
            reference_id,
            source_path,
            str(target_path),
        )
        return target_path
