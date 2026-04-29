"""
Phase 4: resolve operator-facing artifacts from provider-aware metadata (S3/local ArtifactStore).

Strategy:
- **S3** (`storage_provider == "s3"`): **307 Temporary Redirect** to a presigned GET URL (low backend
  bandwidth; matches inventory visual-reference behavior).
- **Local** adapter (`storage_provider == "local"`): **FileResponse** from ``{output_dir}/v3_uploads/{storage_key}``
  with path traversal checks (signed URLs are not supported for local).

Legacy path-only rows (no ``storage_provider`` / incomplete provider fields) use ``storage_path``
under ``v3_uploads`` only when ``artifact_storage_legacy_local_read_enabled`` is true.
Provider-backed access always uses ``storage_key`` (+ bucket for S3); ``storage_path`` is not a
fallback for missing keys (see SQL loaders and :func:`resolve_source_asset_file_response`).

Routes should catch :class:`StoredArtifactAccessError` and map to ``HTTPException``.

This module intentionally separates two responsibilities:
1) **File serving / redirect responses** for operator-facing file endpoints.
2) **Artifact content loading/parsing** for JSON/structured API semantics.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, cast

from fastapi.responses import FileResponse, RedirectResponse, Response

from src.config import load_settings
from src.infrastructure.pipeline.v3_job_executor import RUN_ID
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DURABLE_ARTIFACT_KIND_EXECUTION_LOG,
    DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON,
)
from src.pipeline.execution_log import read_execution_log, read_execution_log_file

logger = logging.getLogger(__name__)


class StoredArtifactAccessError(Exception):
    """Resolution failed; map to HTTP in the route."""

    def __init__(self, status_code: int, detail: str, reason_code: str):
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = detail
        self.reason_code = reason_code


def _provider_meta_complete(meta: Mapping[str, Any]) -> bool:
    prov = (meta.get("storage_provider") or "").strip().lower()
    key = (meta.get("storage_key") or "").strip()
    if not prov or not key:
        return False
    if prov == "s3":
        return bool((meta.get("storage_bucket") or "").strip())
    return True


def _provider_meta_has_any_fields(meta: Mapping[str, Any]) -> bool:
    """True when any provider-aware field is present (including incomplete values)."""
    return bool(
        (meta.get("storage_provider") or "").strip()
        or (meta.get("storage_key") or "").strip()
        or (meta.get("storage_bucket") or "").strip()
    )


def _ensure_s3_bucket_matches_configured(meta: Mapping[str, Any], artifact_store: Any) -> None:
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


def _local_provider_resolved_file_path(*, storage_key: str) -> Path:
    """Resolve ``storage_key`` under ``{output_dir}/v3_uploads`` with path-safety checks."""
    settings = load_settings()
    key = (storage_key or "").strip()
    if not key:
        raise StoredArtifactAccessError(
            404,
            "Stored artifact metadata is incomplete (missing key).",
            "incomplete_metadata",
        )
    base = Path(settings.output_dir) / "v3_uploads"
    resolved_base = base.resolve()
    file_path = (base / key).resolve()
    try:
        file_path.relative_to(resolved_base)
    except ValueError as exc:
        raise StoredArtifactAccessError(
            404,
            "Artifact path failed safety validation.",
            "path_invalid",
        ) from exc
    if not file_path.is_file():
        raise StoredArtifactAccessError(
            404,
            "Stored artifact file not found under local artifact root.",
            "local_file_missing",
        )
    return file_path


def _legacy_v3_uploads_resolved_file_path(*, storage_path: str) -> Path:
    """Validate legacy rows can read ``storage_path`` under ``v3_uploads``; return resolved path."""
    settings = load_settings()
    if not settings.artifact_storage_legacy_local_read_enabled:
        raise StoredArtifactAccessError(
            404,
            "Legacy local file access is disabled; this record has no provider metadata.",
            "legacy_local_disabled",
        )
    raw = (storage_path or "").strip()
    if not raw:
        raise StoredArtifactAccessError(
            404,
            "No storage path on record.",
            "legacy_path_missing",
        )
    base = Path(settings.output_dir) / "v3_uploads"
    resolved_base = base.resolve()
    file_path = (base / raw).resolve()
    try:
        file_path.relative_to(resolved_base)
    except ValueError as exc:
        raise StoredArtifactAccessError(
            404,
            "Legacy asset path failed safety validation.",
            "path_invalid",
        ) from exc
    if not file_path.is_file():
        raise StoredArtifactAccessError(
            404,
            "Legacy asset file not found.",
            "legacy_file_missing",
        )
    return file_path


def presigned_s3_get_url_for_provider_key(
    *,
    storage_key: str,
    storage_bucket: Optional[str],
    artifact_store: Any,
) -> str:
    """Generate a presigned GET URL for S3-backed ``storage_key`` (after bucket validation)."""
    key = (storage_key or "").strip()
    if not key:
        raise StoredArtifactAccessError(
            404,
            "Stored artifact metadata is incomplete (missing key).",
            "incomplete_metadata",
        )
    settings = load_settings()
    meta_dict = {
        "storage_provider": "s3",
        "storage_bucket": storage_bucket,
        "storage_key": key,
    }
    _ensure_s3_bucket_matches_configured(meta_dict, artifact_store)
    sign = getattr(artifact_store, "generate_signed_url", None)
    if not callable(sign):
        raise StoredArtifactAccessError(
            500,
            "Artifact storage is not configured for signed URL generation.",
            "signed_url_unavailable",
        )
    ttl = int(settings.artifact_s3_signed_url_ttl_sec)
    try:
        url = sign(key, ttl)
    except Exception as exc:
        logger.exception(
            "artifact_access signed_url_failed provider=s3 storage_key=%s",
            key,
        )
        raise StoredArtifactAccessError(
            502,
            f"Could not generate download URL for artifact: {exc}",
            "signed_url_failed",
        ) from exc
    logger.info(
        "artifact_access source=s3 mode=presigned_url storage_key=%s ttl_sec=%s",
        key,
        ttl,
    )
    return str(url)


def serve_provider_artifact_response(
    *,
    filename: str,
    media_type: str,
    storage_provider: str,
    storage_key: str,
    storage_bucket: Optional[str],
    artifact_store: Any,
) -> Response:
    """Return redirect (S3) or FileResponse (local) for a provider-backed object."""
    prov = (storage_provider or "").strip().lower()
    key = (storage_key or "").strip()
    if not prov or not key:
        raise StoredArtifactAccessError(
            404,
            "Stored artifact metadata is incomplete (missing provider or key).",
            "incomplete_metadata",
        )
    settings = load_settings()
    meta_dict = {
        "storage_provider": prov,
        "storage_bucket": storage_bucket,
        "storage_key": key,
    }
    _ensure_s3_bucket_matches_configured(meta_dict, artifact_store)

    if prov == "s3":
        url = presigned_s3_get_url_for_provider_key(
            storage_key=key,
            storage_bucket=storage_bucket,
            artifact_store=artifact_store,
        )
        logger.info(
            "artifact_access source=s3 mode=signed_redirect storage_key=%s ttl_sec=%s",
            key,
            int(settings.artifact_s3_signed_url_ttl_sec),
        )
        return RedirectResponse(url=url, status_code=307)

    if prov == "local":
        file_path = _local_provider_resolved_file_path(storage_key=key)
        logger.info(
            "artifact_access source=local mode=file_response storage_key=%s path=%s",
            key,
            str(file_path),
        )
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=filename,
        )

    raise StoredArtifactAccessError(
        400,
        f"Unsupported storage provider: {storage_provider!r}.",
        "unsupported_provider",
    )


def _legacy_v3_uploads_file_response(
    *,
    storage_path: str,
    filename: str,
    media_type: str,
) -> FileResponse:
    file_path = _legacy_v3_uploads_resolved_file_path(storage_path=storage_path)
    logger.info(
        "artifact_access source=legacy_local mode=file_response storage_path=%s",
        (storage_path or "").strip(),
    )
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )


def resolve_source_asset_file_response(
    asset: Any,
    *,
    artifact_store: Any,
) -> Response:
    """Serve a SourceAsset: provider-aware first, then legacy ``storage_path``."""
    prov = (getattr(asset, "storage_provider", None) or "").strip().lower()
    key = (getattr(asset, "storage_key", None) or "").strip()
    bucket = (getattr(asset, "storage_bucket", None) or "").strip() or None

    provider_meta = {
        "storage_provider": prov,
        "storage_key": key,
        "storage_bucket": bucket,
    }

    if _provider_meta_has_any_fields(provider_meta):
        if not _provider_meta_complete(provider_meta):
            raise StoredArtifactAccessError(
                404,
                "Source asset storage metadata is incomplete for provider-backed access.",
                "incomplete_metadata",
            )
        return serve_provider_artifact_response(
            filename=getattr(asset, "original_filename", None) or "file",
            media_type=getattr(asset, "mime_type", None) or "application/octet-stream",
            storage_provider=prov,
            storage_key=key,
            storage_bucket=bucket,
            artifact_store=artifact_store,
        )

    return _legacy_v3_uploads_file_response(
        storage_path=getattr(asset, "storage_path", "") or "",
        filename=getattr(asset, "original_filename", None) or "file",
        media_type=getattr(asset, "mime_type", None) or "application/octet-stream",
    )


def resolve_source_asset_image_display(
    asset: Any,
    *,
    artifact_store: Any,
) -> tuple[Optional[str], bool]:
    """Resolve how the SPA should display a non-HEIC source asset image.

    Returns ``(image_url, requires_authenticated_fetch)``:
    - **S3:** ``(presigned_https_url, False)`` — safe for ``<img src>`` without Bearer.
    - **Local provider / legacy path-only rows:** ``(None, True)`` only after the same path checks
      ``GET .../file`` would pass for readable bytes under ``v3_uploads``. If the file is missing,
      legacy is disabled, or the path is unsafe, raises :class:`StoredArtifactAccessError` (same as
      ``/file`` would for that row).

    **HEIC / HEIF** is handled only in the HTTP route: when a normalized preview exists, the route
    returns the authenticated-fetch strategy pointing at ``.../file`` (which serves the normalized
    JPEG). The helper is not called for HEIC assets.
    """
    prov = (getattr(asset, "storage_provider", None) or "").strip().lower()
    key = (getattr(asset, "storage_key", None) or "").strip()
    bucket = (getattr(asset, "storage_bucket", None) or "").strip() or None

    provider_meta = {
        "storage_provider": prov,
        "storage_key": key,
        "storage_bucket": bucket,
    }

    if _provider_meta_has_any_fields(provider_meta):
        if not _provider_meta_complete(provider_meta):
            raise StoredArtifactAccessError(
                404,
                "Source asset storage metadata is incomplete for provider-backed access.",
                "incomplete_metadata",
            )
        if prov == "s3":
            signed = presigned_s3_get_url_for_provider_key(
                storage_key=key,
                storage_bucket=bucket,
                artifact_store=artifact_store,
            )
            return (signed, False)
        if prov == "local":
            _local_provider_resolved_file_path(storage_key=key)
            return (None, True)
        raise StoredArtifactAccessError(
            400,
            f"Unsupported storage provider: {prov!r}.",
            "unsupported_provider",
        )

    _legacy_v3_uploads_resolved_file_path(
        storage_path=getattr(asset, "storage_path", "") or "",
    )
    return (None, True)


def resolve_visual_reference_file_response(
    ref: Any,
    *,
    artifact_store: Any,
) -> Response:
    """Serve an InventoryVisualReference (same rules as source assets)."""
    prov = (getattr(ref, "storage_provider", None) or "").strip().lower()
    key = (getattr(ref, "storage_key", None) or "").strip()
    bucket = (getattr(ref, "storage_bucket", None) or "").strip() or None

    provider_meta = {
        "storage_provider": prov,
        "storage_key": key,
        "storage_bucket": bucket,
    }

    if _provider_meta_has_any_fields(provider_meta):
        if not _provider_meta_complete(provider_meta):
            raise StoredArtifactAccessError(
                404,
                "Visual reference storage metadata is incomplete for provider-backed access.",
                "incomplete_metadata",
            )
        return serve_provider_artifact_response(
            filename=getattr(ref, "filename", None) or "file",
            media_type=getattr(ref, "mime_type", None) or "application/octet-stream",
            storage_provider=prov,
            storage_key=key,
            storage_bucket=bucket,
            artifact_store=artifact_store,
        )

    return _legacy_v3_uploads_file_response(
        storage_path=getattr(ref, "storage_path", "") or "",
        filename=getattr(ref, "filename", None) or "file",
        media_type=getattr(ref, "mime_type", None) or "application/octet-stream",
    )


def load_artifact_content_from_provider_meta(
    meta: Mapping[str, Any],
    *,
    artifact_store: Any,
    label: str,
    hard_max_bytes: Optional[int] = None,
) -> bytes:
    """Load raw bytes using provider metadata.

    Without ``hard_max_bytes``, chooses ``get_object`` vs ``download_to_path`` using
    ``artifact_store_max_in_memory_get_bytes`` and may load arbitrarily large objects.

    With ``hard_max_bytes`` (e.g. JSON durable payloads), rejects objects larger than the cap
    **before** reading the full body into memory when ``object_size_bytes`` succeeds; when
    size is unknown, downloads to a tempfile, checks ``stat().st_size``, and raises without
    ``read_bytes`` if over the cap.
    """
    if not _provider_meta_complete(meta):
        raise StoredArtifactAccessError(
            404,
            f"{label}: incomplete storage metadata (provider, key, and for S3 a bucket are required).",
            "incomplete_metadata",
        )
    _ensure_s3_bucket_matches_configured(meta, artifact_store)
    key = (meta.get("storage_key") or "").strip()
    prov = (meta.get("storage_provider") or "").strip().lower()
    bucket = (meta.get("storage_bucket") or "").strip() or None
    dl_bucket = bucket if prov == "s3" else None
    settings = load_settings()
    mem_threshold = int(settings.artifact_store_max_in_memory_get_bytes)

    size_known: Optional[int] = None
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


def read_execution_log_events_for_job(
    job: Any,
    *,
    artifact_store: Any,
) -> List[Dict[str, Any]]:
    settings = load_settings()
    rj = getattr(job, "result_json", None) or {}
    durable = rj.get("durable_artifacts") or {}
    meta = durable.get(DURABLE_ARTIFACT_KIND_EXECUTION_LOG)
    if meta is not None and not _provider_meta_complete(meta):
        raise StoredArtifactAccessError(
            404,
            "Execution log durable artifact metadata is incomplete (missing provider, key, or bucket).",
            "incomplete_metadata",
        )

    if meta and _provider_meta_complete(meta):
        _ensure_s3_bucket_matches_configured(meta, artifact_store)
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


def fetch_json_from_durable_meta(
    meta: Mapping[str, Any],
    *,
    artifact_store: Any,
    label: str,
) -> Dict[str, Any]:
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
    job: Optional[Any] = None,
    job_repo: Any,
    artifact_store: Any,
) -> Optional[Dict[str, Any]]:
    """Load hybrid_report dict: durable metadata first, then legacy disk when allowed.

    Used for best-effort enrichment (returns None on failure). For strict API semantics use
    :func:`load_hybrid_report_json_for_api`.
    """
    settings = load_settings()
    j = job if job is not None else job_repo.get_by_id(job_id)
    if j is None:
        return None
    durable = (getattr(j, "result_json", None) or {}).get("durable_artifacts") or {}
    meta = durable.get(DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON)
    if meta and _provider_meta_complete(meta):
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


def cast_mapping(meta: Any) -> Mapping[str, Any]:
    return meta if isinstance(meta, Mapping) else {}


def load_hybrid_report_json_for_api(
    job: Any,
    *,
    artifact_store: Any,
) -> Dict[str, Any]:
    """Strict load for GET hybrid-report: durable required when present and complete; else legacy."""
    settings = load_settings()
    job_id = getattr(job, "id", "")
    durable = (getattr(job, "result_json", None) or {}).get("durable_artifacts") or {}
    meta = durable.get(DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON)
    if meta is not None and not _provider_meta_complete(cast_mapping(meta)):
        raise StoredArtifactAccessError(
            404,
            "Hybrid report durable artifact metadata is incomplete (missing provider, key, or bucket).",
            "incomplete_metadata",
        )
    if meta and _provider_meta_complete(cast_mapping(meta)):
        data = fetch_json_from_durable_meta(
            cast_mapping(meta),
            artifact_store=artifact_store,
            label="Hybrid report",
        )
        logger.info(
            "hybrid_report_api source=durable_metadata job_id=%s",
            job_id,
        )
        return data

    if not settings.artifact_storage_legacy_local_read_enabled:
        raise StoredArtifactAccessError(
            404,
            "Hybrid report is not available: incomplete or missing durable metadata and legacy local read is disabled.",
            "no_durable_metadata_legacy_disabled",
        )
    path = Path(settings.output_dir) / job_id / RUN_ID / "hybrid_report.json"
    if not path.is_file():
        raise StoredArtifactAccessError(
            404,
            "Hybrid report file not found (legacy path).",
            "legacy_file_missing",
        )
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise StoredArtifactAccessError(
            502,
            "Hybrid report file could not be read.",
            "legacy_read_failed",
        ) from exc
    if not isinstance(data, dict):
        raise StoredArtifactAccessError(502, "Hybrid report payload invalid.", "invalid_json")
    logger.info(
        "hybrid_report_api source=legacy_local path=%s job_id=%s",
        str(path),
        job_id,
    )
    return data
