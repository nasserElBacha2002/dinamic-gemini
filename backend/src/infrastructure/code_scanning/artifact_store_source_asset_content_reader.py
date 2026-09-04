"""Load source asset bytes via ArtifactStore (GCS/S3/local)."""

from __future__ import annotations

import logging
import time
from typing import Any

from src.domain.assets.entities import SourceAsset
from src.infrastructure.storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)

_DEFAULT_SLOW_WARNING_MS = 10_000


def _storage_backend_label(store: ArtifactStore) -> str:
    provider = getattr(store, "storage_provider", None)
    if isinstance(provider, str) and provider.strip():
        return provider.strip().upper()
    name = type(store).__name__
    lowered = name.lower()
    if "gcs" in lowered:
        return "GCS"
    if "s3" in lowered:
        return "S3"
    if "local" in lowered or "v3" in lowered:
        return "LOCAL"
    return name


def _bucket_label(store: ArtifactStore) -> str | None:
    bucket = getattr(store, "bucket", None)
    if isinstance(bucket, str) and bucket.strip():
        return bucket.strip()
    return None


def _record_storage_metrics(
    *,
    backend: str,
    outcome: str,
    duration_seconds: float,
    slow: bool,
) -> None:
    try:
        from src.observability.metrics.instruments import record_storage_fetch

        record_storage_fetch(
            backend=backend,
            outcome=outcome,
            duration_seconds=duration_seconds,
            slow=slow,
        )
    except Exception:
        # Metrics must never break asset reads.
        logger.debug("storage_fetch.metrics_skipped", exc_info=True)


class ArtifactStoreSourceAssetContentReader:
    """Read asset bytes once; expose last-fetch diagnostics for observability.

    Does not perform extra HEAD/metadata calls — timing wraps the existing
    ``ArtifactStore.get_object`` path only.
    """

    def __init__(
        self,
        artifact_store: ArtifactStore,
        *,
        slow_warning_ms: int = _DEFAULT_SLOW_WARNING_MS,
        monotonic_fn=time.monotonic,
    ) -> None:
        self._store = artifact_store
        self._slow_warning_ms = max(1, int(slow_warning_ms))
        self._monotonic = monotonic_fn
        self._last_fetch: dict[str, Any] | None = None

    @property
    def last_fetch_diagnostics(self) -> dict[str, Any] | None:
        return dict(self._last_fetch) if self._last_fetch else None

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        key = (asset.storage_key or "").strip()
        if not key:
            raise ValueError(f"Source asset {asset.id} has no storage_key")

        backend = _storage_backend_label(self._store)
        bucket = _bucket_label(self._store)
        started = self._monotonic()
        attempt = 1
        try:
            downloaded = self._store.get_object(key)
        except Exception as exc:
            duration_ms = max(0, int((self._monotonic() - started) * 1000))
            diag = {
                "asset_id": str(asset.id),
                "storage_backend": backend,
                "bucket": bucket,
                "object_key": key[:240],
                "byte_length": None,
                "duration_ms": duration_ms,
                "storage_fetch_ms": duration_ms,
                "attempt": attempt,
                "success": False,
                "retry_status": "unknown",
                "error_type": type(exc).__name__,
            }
            self._last_fetch = diag
            _record_storage_metrics(
                backend=backend,
                outcome="failed",
                duration_seconds=duration_ms / 1000.0,
                slow=duration_ms >= self._slow_warning_ms,
            )
            logger.warning(
                "asset.storage_fetch_failed asset_id=%s storage_backend=%s bucket=%s "
                "duration_ms=%s attempt=%s error=%s",
                asset.id,
                backend,
                bucket or "-",
                duration_ms,
                attempt,
                type(exc).__name__,
            )
            logger.warning(
                "code_scan storage_read_failed asset_id=%s aisle_id=%s error=%s",
                asset.id,
                asset.aisle_id,
                type(exc).__name__,
            )
            raise FileNotFoundError(f"Storage object not found for asset {asset.id}") from exc

        duration_ms = max(0, int((self._monotonic() - started) * 1000))
        content = downloaded.content
        byte_length = len(content) if content else 0
        slow = duration_ms >= self._slow_warning_ms
        diag = {
            "asset_id": str(asset.id),
            "storage_backend": backend,
            "bucket": bucket,
            "object_key": key[:240],
            "byte_length": byte_length,
            "duration_ms": duration_ms,
            "storage_fetch_ms": duration_ms,
            "attempt": attempt,
            "success": True,
            "retry_status": "unknown",
            "slow": slow,
        }
        # Prefer adapter-reported phase timings when present (no extra I/O).
        last_gcs = getattr(self._store, "last_get_object_timings", None)
        if isinstance(last_gcs, dict):
            for field in (
                "download_ms",
                "metadata_lookup_ms",
                "total_storage_ms",
                "credentials_expired_at_start",
            ):
                if field in last_gcs:
                    diag[field] = last_gcs[field]
            if "retry_status" in last_gcs:
                diag["retry_status"] = last_gcs["retry_status"]

        self._last_fetch = diag
        _record_storage_metrics(
            backend=backend,
            outcome="ok",
            duration_seconds=duration_ms / 1000.0,
            slow=slow,
        )
        logger.info(
            "asset.storage_fetch_completed asset_id=%s storage_backend=%s bucket=%s "
            "byte_length=%s duration_ms=%s attempt=%s",
            asset.id,
            backend,
            bucket or "-",
            byte_length,
            duration_ms,
            attempt,
        )
        if slow:
            logger.warning(
                "asset.storage_fetch_slow asset_id=%s storage_backend=%s bucket=%s "
                "byte_length=%s duration_ms=%s threshold_ms=%s",
                asset.id,
                backend,
                bucket or "-",
                byte_length,
                duration_ms,
                self._slow_warning_ms,
            )

        if not content:
            raise ValueError(f"Empty storage object for asset {asset.id}")
        return content
