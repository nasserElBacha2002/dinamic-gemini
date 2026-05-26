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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from src.config import load_settings
from src.infrastructure.pipeline.v3_job_executor import RUN_ID
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DURABLE_ARTIFACT_KIND_EXECUTION_LOG,
    DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON,
)
from src.pipeline.execution_log import read_execution_log, read_execution_log_file

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
    if prov in ("s3", "gcs"):
        return bool((meta.get("storage_bucket") or "").strip())
    return True


def ensure_remote_bucket_matches_configured(meta: Mapping[str, Any], artifact_store: Any) -> None:
    """Validate record bucket matches configured S3/GCS adapter bucket when both are set."""
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


@dataclass(frozen=True)
class _ArtifactByteFetchParams:
    """Bundled object-store fetch context (B8.4 — avoids huge nested closures)."""

    artifact_store: Any
    key: str
    prov: str
    bucket_display: str
    dl_bucket: str | None
    label: str
    hard_max_bytes: int | None


def _artifact_get_object_bytes(p: _ArtifactByteFetchParams) -> bytes:
    try:
        downloaded = p.artifact_store.get_object(p.key)
    except Exception as exc:
        logger.exception(
            "%s durable_fetch_failed mode=get_object provider=%s bucket=%s storage_key=%s",
            p.label,
            p.prov,
            p.bucket_display,
            p.key,
        )
        raise StoredArtifactAccessError(
            502,
            f"{p.label} could not be loaded from object storage (missing object or read error).",
            "durable_fetch_failed",
        ) from exc
    data = downloaded.content
    if p.hard_max_bytes is not None and len(data) > p.hard_max_bytes:
        raise StoredArtifactAccessError(
            413,
            f"{p.label} exceeds configured max load size ({p.hard_max_bytes} bytes).",
            "payload_too_large",
        )
    logger.info(
        "%s artifact_bytes_loaded mode=get_object provider=%s bucket=%s storage_key=%s bytes=%s",
        p.label,
        p.prov,
        p.bucket_display,
        p.key,
        len(data),
    )
    return cast(bytes, data)


def _artifact_download_bytes_via_temp(p: _ArtifactByteFetchParams) -> bytes:
    fd, tmp_name = tempfile.mkstemp(prefix="artifact_", suffix=".bin")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        p.artifact_store.download_to_path(p.key, tmp_path, bucket=p.dl_bucket)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        logger.exception(
            "%s durable_fetch_failed mode=download_to_path provider=%s bucket=%s storage_key=%s",
            p.label,
            p.prov,
            p.bucket_display,
            p.key,
        )
        raise StoredArtifactAccessError(
            502,
            f"{p.label} could not be loaded from object storage (missing object or read error).",
            "durable_fetch_failed",
        ) from exc
    try:
        on_disk = int(tmp_path.stat().st_size)
        if p.hard_max_bytes is not None and on_disk > p.hard_max_bytes:
            logger.info(
                "%s payload_too_large (on_disk) provider=%s storage_key=%s size=%s max=%s",
                p.label,
                p.prov,
                p.key,
                on_disk,
                p.hard_max_bytes,
            )
            raise StoredArtifactAccessError(
                413,
                f"{p.label} exceeds configured max load size ({p.hard_max_bytes} bytes).",
                "payload_too_large",
            )
        data = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info(
        "%s artifact_bytes_loaded mode=download_temp provider=%s bucket=%s storage_key=%s bytes=%s",
        p.label,
        p.prov,
        p.bucket_display,
        p.key,
        len(data),
    )
    return cast(bytes, data)


def _artifact_fetch_bytes_by_policy(
    p: _ArtifactByteFetchParams,
    *,
    size_known: int | None,
    mem_threshold: int,
) -> bytes:
    """Apply in-memory vs tempfile policy (same branches as pre–B8.4 ``load_artifact_content_from_provider_meta``)."""
    if p.hard_max_bytes is not None:
        if size_known is not None:
            if size_known <= mem_threshold:
                return _artifact_get_object_bytes(p)
            return _artifact_download_bytes_via_temp(p)
        logger.info(
            "%s json_load size_unknown will_download_then_stat storage_key=%s max=%s",
            p.label,
            p.key,
            p.hard_max_bytes,
        )
        return _artifact_download_bytes_via_temp(p)

    if size_known is not None and 0 <= size_known <= mem_threshold:
        return _artifact_get_object_bytes(p)
    if size_known is not None and size_known > mem_threshold:
        return _artifact_download_bytes_via_temp(p)

    logger.warning(
        "%s object_size_bytes unavailable; using download_temp storage_key=%s",
        p.label,
        p.key,
    )
    return _artifact_download_bytes_via_temp(p)


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
    ensure_remote_bucket_matches_configured(meta, artifact_store)
    key = (meta.get("storage_key") or "").strip()
    prov = (meta.get("storage_provider") or "").strip().lower()
    bucket = (meta.get("storage_bucket") or "").strip() or None
    dl_bucket = bucket if prov == "s3" else None
    bucket_display = bucket or ""
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
            bucket_display,
            key,
            size_known,
            hard_max_bytes,
        )
        raise StoredArtifactAccessError(
            413,
            f"{label} exceeds configured max load size ({hard_max_bytes} bytes).",
            "payload_too_large",
        )

    fetch_params = _ArtifactByteFetchParams(
        artifact_store=artifact_store,
        key=key,
        prov=prov,
        bucket_display=bucket_display,
        dl_bucket=dl_bucket,
        label=label,
        hard_max_bytes=hard_max_bytes,
    )
    return _artifact_fetch_bytes_by_policy(
        fetch_params,
        size_known=size_known,
        mem_threshold=mem_threshold,
    )


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


def read_execution_log_events_for_job(job: Any, *, artifact_store: Any) -> list[dict[str, Any]]:
    """Load parsed execution_log.jsonl events for one job (durable metadata first, else legacy run_dir).

    Raises :class:`StoredArtifactAccessError` when durable metadata is incomplete, fetch fails, or
    legacy read is disabled / missing — same contract as v3 execution-log HTTP surfaces.
    """
    settings = load_settings()
    rj = getattr(job, "result_json", None) or {}
    durable = rj.get("durable_artifacts") or {}
    meta = durable.get(DURABLE_ARTIFACT_KIND_EXECUTION_LOG)
    if meta is not None and not provider_meta_complete(meta):
        raise StoredArtifactAccessError(
            404,
            "Execution log durable artifact metadata is incomplete (missing provider, key, or bucket).",
            "incomplete_metadata",
        )

    if meta and provider_meta_complete(meta):
        ensure_remote_bucket_matches_configured(meta, artifact_store)
        prov = (meta.get("storage_provider") or "").strip().lower()
        key = (meta.get("storage_key") or "").strip()
        bucket = (meta.get("storage_bucket") or "").strip() or None
        dl_bucket = bucket if prov == "s3" else None
        logger.info(
            "execution_log_resolve source=durable_download provider=%s bucket=%s storage_key=%s job_id=%s",
            prov,
            bucket or "",
            key,
            getattr(job, "id", "?"),
        )
        fd, tmp_name = tempfile.mkstemp(prefix="exec_log_", suffix=".jsonl")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            artifact_store.download_to_path(key, tmp_path, bucket=dl_bucket)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            logger.exception(
                "execution_log durable_fetch_failed provider=%s bucket=%s storage_key=%s job_id=%s",
                prov,
                bucket or "",
                key,
                getattr(job, "id", "?"),
            )
            raise StoredArtifactAccessError(
                502,
                "Execution log could not be loaded from object storage.",
                "durable_fetch_failed",
            ) from exc
        try:
            return read_execution_log_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    if not settings.artifact_storage_legacy_local_read_enabled:
        raise StoredArtifactAccessError(
            404,
            "Execution log is not available: incomplete or missing durable metadata and legacy local read is disabled.",
            "no_durable_metadata_legacy_disabled",
        )

    run_dir = Path(settings.output_dir) / getattr(job, "id", "") / RUN_ID
    logger.info(
        "execution_log_resolve source=legacy_local run_dir=%s job_id=%s",
        str(run_dir),
        getattr(job, "id", "?"),
    )
    return read_execution_log(run_dir)


def try_read_execution_log_events_for_job(job: Any, *, artifact_store: Any) -> list[dict[str, Any]] | None:
    """Best-effort execution log load for read models (no exception on missing/failed artifacts)."""
    try:
        return read_execution_log_events_for_job(job, artifact_store=artifact_store)
    except StoredArtifactAccessError as exc:
        logger.debug(
            "execution_log_try_load_failed job_id=%s reason=%s",
            getattr(job, "id", "?"),
            exc.reason_code,
        )
        return None
    except Exception as exc:
        logger.debug(
            "execution_log_try_load_failed job_id=%s err=%s",
            getattr(job, "id", "?"),
            exc,
        )
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
