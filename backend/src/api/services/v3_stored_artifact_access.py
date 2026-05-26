"""
Phase 4: resolve operator-facing artifacts from provider-aware metadata (S3/GCS/local ArtifactStore).

Strategy:
- **S3 / GCS** (`storage_provider` in ``s3``, ``gcs``): **307 Temporary Redirect** to a signed GET URL
  (low backend bandwidth; matches inventory visual-reference behavior).
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
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi.responses import FileResponse, RedirectResponse, Response

from src.config import load_settings
from src.infrastructure.artifacts.stored_artifact_reader import (
    StoredArtifactAccessError,
    cast_mapping,
    ensure_s3_bucket_matches_configured,
    fetch_json_from_durable_meta,
    provider_meta_complete,
)
from src.infrastructure.pipeline.v3_job_executor import RUN_ID
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON,
)

logger = logging.getLogger(__name__)


def _provider_meta_has_any_fields(meta: Mapping[str, Any]) -> bool:
    """True when any provider-aware field is present (including incomplete values)."""
    return bool(
        (meta.get("storage_provider") or "").strip()
        or (meta.get("storage_key") or "").strip()
        or (meta.get("storage_bucket") or "").strip()
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
    storage_bucket: str | None,
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
    ensure_s3_bucket_matches_configured(meta_dict, artifact_store)
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


def presigned_gcs_get_url_for_provider_key(
    *,
    storage_key: str,
    storage_bucket: str | None,
    artifact_store: Any,
) -> str:
    """Generate a signed GET URL for GCS-backed ``storage_key`` (after bucket validation)."""
    key = (storage_key or "").strip()
    if not key:
        raise StoredArtifactAccessError(
            404,
            "Stored artifact metadata is incomplete (missing key).",
            "incomplete_metadata",
        )
    settings = load_settings()
    meta_dict = {
        "storage_provider": "gcs",
        "storage_bucket": storage_bucket,
        "storage_key": key,
    }
    ensure_s3_bucket_matches_configured(meta_dict, artifact_store)
    sign = getattr(artifact_store, "generate_signed_url", None)
    if not callable(sign):
        raise StoredArtifactAccessError(
            500,
            "Artifact storage is not configured for signed URL generation.",
            "signed_url_unavailable",
        )
    ttl = int(settings.artifact_gcs_signed_url_ttl_sec)
    try:
        url = sign(key, ttl)
    except Exception as exc:
        logger.exception(
            "artifact_access signed_url_failed provider=gcs storage_key=%s",
            key,
        )
        raise StoredArtifactAccessError(
            502,
            f"Could not generate download URL for artifact: {exc}",
            "signed_url_failed",
        ) from exc
    logger.info(
        "artifact_access source=gcs mode=signed_url storage_key=%s ttl_sec=%s",
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
    storage_bucket: str | None,
    artifact_store: Any,
) -> Response:
    """Return redirect (S3/GCS) or FileResponse (local) for a provider-backed object."""
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
    ensure_s3_bucket_matches_configured(meta_dict, artifact_store)

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

    if prov == "gcs":
        url = presigned_gcs_get_url_for_provider_key(
            storage_key=key,
            storage_bucket=storage_bucket,
            artifact_store=artifact_store,
        )
        logger.info(
            "artifact_access source=gcs mode=signed_redirect storage_key=%s ttl_sec=%s",
            key,
            int(settings.artifact_gcs_signed_url_ttl_sec),
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
        if not provider_meta_complete(provider_meta):
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
) -> tuple[str | None, bool]:
    """Resolve how the SPA should display a non-HEIC source asset image.

    Returns ``(image_url, requires_authenticated_fetch)``:
    - **S3 / GCS:** ``(signed_https_url, False)`` — safe for ``<img src>`` without Bearer.
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
        if not provider_meta_complete(provider_meta):
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
        if prov == "gcs":
            signed = presigned_gcs_get_url_for_provider_key(
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


def resolve_reference_image_file_response(
    ref: Any,
    *,
    artifact_store: Any,
) -> Response:
    """Serve a stored reference image record (supplier images and legacy-shaped rows; same rules as source assets)."""
    prov = (getattr(ref, "storage_provider", None) or "").strip().lower()
    key = (getattr(ref, "storage_key", None) or "").strip()
    bucket = (getattr(ref, "storage_bucket", None) or "").strip() or None

    provider_meta = {
        "storage_provider": prov,
        "storage_key": key,
        "storage_bucket": bucket,
    }

    if _provider_meta_has_any_fields(provider_meta):
        if not provider_meta_complete(provider_meta):
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


def resolve_supplier_reference_image_file_response(
    image: Any,
    *,
    artifact_store: Any,
) -> Response:
    """Serve a SupplierReferenceImage using the same provider / legacy rules as other reference images."""
    return resolve_reference_image_file_response(image, artifact_store=artifact_store)


def load_hybrid_report_json_for_api(
    job: Any,
    *,
    artifact_store: Any,
) -> dict[str, Any]:
    """Strict load for GET hybrid-report: durable required when present and complete; else legacy."""
    settings = load_settings()
    job_id = getattr(job, "id", "")
    durable = (getattr(job, "result_json", None) or {}).get("durable_artifacts") or {}
    meta = durable.get(DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON)
    if meta is not None and not provider_meta_complete(cast_mapping(meta)):
        raise StoredArtifactAccessError(
            404,
            "Hybrid report durable artifact metadata is incomplete (missing provider, key, or bucket).",
            "incomplete_metadata",
        )
    if meta and provider_meta_complete(cast_mapping(meta)):
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
