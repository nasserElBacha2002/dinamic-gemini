"""
Phase 4: resolve operator-facing artifacts from provider-aware metadata (S3/local ArtifactStore).

Strategy:
- **S3** (`storage_provider == "s3"`): **307 Temporary Redirect** to a presigned GET URL (low backend
  bandwidth; matches inventory visual-reference behavior).
- **Local** adapter (`storage_provider == "local"`): **FileResponse** from ``{output_dir}/v3_uploads/{storage_key}``
  with path traversal checks (signed URLs are not supported for local).

Legacy path-only records use `storage_path` under `v3_uploads` only when
``artifact_storage_legacy_local_read_enabled`` is true.

Routes should catch :class:`StoredArtifactAccessError` and map to ``HTTPException``.

This module intentionally separates two responsibilities:
1) **File serving / redirect responses** for operator-facing file endpoints.
2) **Artifact content loading/parsing** for JSON/structured API semantics.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from fastapi.responses import FileResponse, RedirectResponse, Response

from src.config import load_settings
from src.infrastructure.pipeline.v3_job_executor import RUN_ID
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DURABLE_ARTIFACT_KIND_EXECUTION_LOG,
    DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON,
)
from src.pipeline.execution_log import read_execution_log, read_execution_log_bytes

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
            "artifact_access source=s3 mode=signed_redirect storage_key=%s ttl_sec=%s",
            key,
            ttl,
        )
        return RedirectResponse(url=url, status_code=307)

    if prov == "local":
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
    logger.info(
        "artifact_access source=legacy_local mode=file_response storage_path=%s",
        raw,
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
) -> bytes:
    """Content-loading helper: fetch raw bytes from ArtifactStore using provider metadata."""
    if not _provider_meta_complete(meta):
        raise StoredArtifactAccessError(
            404,
            f"{label}: incomplete storage metadata.",
            "incomplete_metadata",
        )
    _ensure_s3_bucket_matches_configured(meta, artifact_store)
    key = (meta.get("storage_key") or "").strip()
    try:
        downloaded = artifact_store.get_object(key)
    except Exception as exc:
        logger.exception(
            "%s durable_fetch_failed storage_key=%s",
            label,
            key,
        )
        raise StoredArtifactAccessError(
            502,
            f"{label} could not be loaded from object storage.",
            "durable_fetch_failed",
        ) from exc
    return downloaded.content


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
        logger.info(
            "execution_log_resolve source=durable_metadata provider=%s storage_key=%s job_id=%s",
            prov,
            key,
            getattr(job, "id", "?"),
        )
        raw = load_artifact_content_from_provider_meta(
            meta,
            artifact_store=artifact_store,
            label="Execution log",
        )
        return read_execution_log_bytes(raw)

    if not settings.artifact_storage_legacy_local_read_enabled:
        raise StoredArtifactAccessError(
            404,
            "Execution log is not available: no durable artifact metadata and legacy local read is disabled.",
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
    raw = load_artifact_content_from_provider_meta(
        meta,
        artifact_store=artifact_store,
        label=label,
    )
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StoredArtifactAccessError(
            502,
            f"{label} payload is not valid JSON.",
            "invalid_json",
        ) from exc


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
            "Hybrid report is not available: no durable artifact metadata and legacy local read is disabled.",
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
