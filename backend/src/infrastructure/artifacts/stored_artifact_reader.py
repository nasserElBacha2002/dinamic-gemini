"""
Durable and legacy loading of stored JSON artifacts (hybrid report, etc.).

Shared with :mod:`src.api.services.v3_stored_artifact_access` for HTTP mapping; the application
layer depends only on :class:`src.application.ports.stored_artifact_reader.StoredArtifactReader`.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from src.config import load_settings
from src.infrastructure.pipeline.v3_job_executor import RUN_ID
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON,
)

logger = logging.getLogger(__name__)


class StoredArtifactAccessError(Exception):
    """Resolution failed; API routes map this to HTTP."""

    def __init__(self, status_code: int, detail: str, reason_code: str):
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = detail
        self.reason_code = reason_code


def provider_meta_complete(meta: Mapping[str, Any]) -> bool:
    prov = (meta.get("storage_provider") or "").strip().lower()
    key = (meta.get("storage_key") or "").strip()
    if not prov or not key:
        return False
    if prov == "s3":
        return bool((meta.get("storage_bucket") or "").strip())
    return True


def ensure_s3_bucket_matches_configured(meta: Mapping[str, Any], artifact_store: Any) -> None:
    configured = (getattr(artifact_store, "bucket", None) or "").strip()
    record_bucket = (meta.get("storage_bucket") or "").strip()
    if not configured or not record_bucket:
        return
    if record_bucket != configured:
        raise StoredArtifactAccessError(
            409,
            f"Artifact bucket metadata does not match configured bucket (record={record_bucket!r}).",
            "bucket_mismatch",
        )


def load_artifact_content_from_provider_meta(
    meta: Mapping[str, Any],
    *,
    artifact_store: Any,
    label: str,
    hard_max_bytes: int | None = None,
) -> bytes:
    """Load raw bytes using provider metadata."""
    if not provider_meta_complete(meta):
        raise StoredArtifactAccessError(
            404,
            f"{label}: incomplete storage metadata (provider, key, and for S3 a bucket are required).",
            "incomplete_metadata",
        )
    ensure_s3_bucket_matches_configured(meta, artifact_store)
    key = (meta.get("storage_key") or "").strip()
    prov = (meta.get("storage_provider") or "").strip().lower()
    bucket = (meta.get("storage_bucket") or "").strip() or None
    dl_bucket = bucket if prov == "s3" else None
    settings = load_settings()
    mem_threshold = int(settings.artifact_store_max_in_memory_get_bytes)

    size_known: int | None = None
    try:
        size_known = int(artifact_store.object_size_bytes(key, bucket=dl_bucket))
    except Exception as head_exc:
        logger.warning(
            "%s object_size_bytes failed storage_key=%s provider=%s: %s",
            label,
            key,
            prov,
            head_exc,
        )

    if hard_max_bytes is not None and size_known is not None and size_known > hard_max_bytes:
        logger.info(
            "%s payload_too_large (head) provider=%s bucket=%s storage_key=%s size=%s max=%s",
            label,
            prov,
            bucket or "",
            key,
            size_known,
            hard_max_bytes,
        )
        raise StoredArtifactAccessError(
            413,
            f"{label} exceeds configured max load size ({hard_max_bytes} bytes).",
            "payload_too_large",
        )

    def _get_object_bytes() -> bytes:
        try:
            downloaded = artifact_store.get_object(key)
        except Exception as exc:
            logger.exception(
                "%s durable_fetch_failed mode=get_object provider=%s bucket=%s storage_key=%s",
                label,
                prov,
                bucket or "",
                key,
            )
            raise StoredArtifactAccessError(
                502,
                f"{label} could not be loaded from object storage (missing object or read error).",
                "durable_fetch_failed",
            ) from exc
        data = downloaded.content
        if hard_max_bytes is not None and len(data) > hard_max_bytes:
            raise StoredArtifactAccessError(
                413,
                f"{label} exceeds configured max load size ({hard_max_bytes} bytes).",
                "payload_too_large",
            )
        logger.info(
            "%s artifact_bytes_loaded mode=get_object provider=%s bucket=%s storage_key=%s bytes=%s",
            label,
            prov,
            bucket or "",
            key,
            len(data),
        )
        return cast(bytes, data)

    def _download_via_tempfile() -> bytes:
        fd, tmp_name = tempfile.mkstemp(prefix="artifact_", suffix=".bin")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            artifact_store.download_to_path(key, tmp_path, bucket=dl_bucket)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            logger.exception(
                "%s durable_fetch_failed mode=download_to_path provider=%s bucket=%s storage_key=%s",
                label,
                prov,
                bucket or "",
                key,
            )
            raise StoredArtifactAccessError(
                502,
                f"{label} could not be loaded from object storage (missing object or read error).",
                "durable_fetch_failed",
            ) from exc
        try:
            on_disk = int(tmp_path.stat().st_size)
            if hard_max_bytes is not None and on_disk > hard_max_bytes:
                logger.info(
                    "%s payload_too_large (on_disk) provider=%s storage_key=%s size=%s max=%s",
                    label,
                    prov,
                    key,
                    on_disk,
                    hard_max_bytes,
                )
                raise StoredArtifactAccessError(
                    413,
                    f"{label} exceeds configured max load size ({hard_max_bytes} bytes).",
                    "payload_too_large",
                )
            data = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
        logger.info(
            "%s artifact_bytes_loaded mode=download_temp provider=%s bucket=%s storage_key=%s bytes=%s",
            label,
            prov,
            bucket or "",
            key,
            len(data),
        )
        return cast(bytes, data)

    if hard_max_bytes is not None:
        if size_known is not None:
            if size_known <= mem_threshold:
                return _get_object_bytes()
            return _download_via_tempfile()
        logger.info(
            "%s json_load size_unknown will_download_then_stat storage_key=%s max=%s",
            label,
            key,
            hard_max_bytes,
        )
        return _download_via_tempfile()

    if size_known is not None and 0 <= size_known <= mem_threshold:
        return _get_object_bytes()
    if size_known is not None and size_known > mem_threshold:
        return _download_via_tempfile()

    logger.warning(
        "%s object_size_bytes unavailable; using download_temp storage_key=%s",
        label,
        key,
    )
    return _download_via_tempfile()


def cast_mapping(meta: Any) -> Mapping[str, Any]:
    return meta if isinstance(meta, Mapping) else {}


def fetch_json_from_durable_meta(
    meta: Mapping[str, Any],
    *,
    artifact_store: Any,
    label: str,
) -> dict[str, Any]:
    settings = load_settings()
    max_json = int(settings.artifact_store_max_json_load_bytes)
    raw = load_artifact_content_from_provider_meta(
        meta,
        artifact_store=artifact_store,
        label=label,
        hard_max_bytes=max_json,
    )
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StoredArtifactAccessError(
            502,
            f"{label} payload is not valid JSON.",
            "invalid_json",
        ) from exc
    return parsed if isinstance(parsed, dict) else {}


def load_hybrid_report_json_for_job(
    job_id: str,
    *,
    job: Any | None = None,
    job_repo: Any,
    artifact_store: Any,
) -> dict[str, Any] | None:
    """Load hybrid_report dict: durable metadata first, then legacy disk when allowed."""
    settings = load_settings()
    j = job if job is not None else job_repo.get_by_id(job_id)
    if j is None:
        return None
    durable = (getattr(j, "result_json", None) or {}).get("durable_artifacts") or {}
    meta = durable.get(DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON)
    if meta and provider_meta_complete(meta):
        try:
            data = fetch_json_from_durable_meta(
                cast_mapping(meta),
                artifact_store=artifact_store,
                label="hybrid_report",
            )
            logger.info(
                "hybrid_report_resolve source=durable_metadata job_id=%s storage_key=%s",
                job_id,
                meta.get("storage_key"),
            )
            return data
        except StoredArtifactAccessError as e:
            logger.warning(
                "hybrid_report_resolve durable_failed job_id=%s reason=%s",
                job_id,
                e.reason_code,
            )

    if not settings.artifact_storage_legacy_local_read_enabled:
        return None
    path = Path(settings.output_dir) / job_id / RUN_ID / "hybrid_report.json"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        logger.info(
            "hybrid_report_resolve source=legacy_local path=%s job_id=%s",
            str(path),
            job_id,
        )
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.debug("hybrid_report legacy load failed job_id=%s: %s", job_id, exc)
        return None


class DefaultStoredArtifactReader:
    """Wires job + artifact store for :class:`StoredArtifactReader` (composition root / tests)."""

    def __init__(self, job_repo: Any, artifact_store: Any) -> None:
        self._job_repo = job_repo
        self._artifact_store = artifact_store

    def load_hybrid_report_json_for_job(self, job_id: str) -> dict[str, Any] | None:
        return load_hybrid_report_json_for_job(
            job_id,
            job_repo=self._job_repo,
            artifact_store=self._artifact_store,
        )
