"""
v3 shared helpers: response mappers, exception mapping, HEIC/normalized path resolution.
Used by v3 route modules (inventories, aisles, assets, positions, reviews).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from fastapi import HTTPException

from src.config import load_settings
from src.utils.validation import validate_relative_path

from src.api.schemas.aisle_schemas import AisleResponse, AisleJobSummary
from src.api.schemas.asset_schemas import SourceAssetResponse
from src.api.schemas.processing_schemas import AisleStatusResponse, JobSummary
from src.api.schemas.inventory_schemas import InventoryResponse
from src.api.schemas.position_schemas import (
    EvidenceResponse,
    PositionSummaryResponse,
    ReviewActionResponse,
)
from src.application.ports.repositories import JobRepository
from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    PositionNotFoundError,
    ProductNotFoundError,
    PositionDeletedError,
)
from src.application.use_cases.get_aisle_processing_status import AisleProcessingStatusResult
from src.application.use_cases.confirm_position import ConfirmPositionUseCase
from src.application.use_cases.update_product_quantity import UpdateProductQuantityUseCase
from src.application.use_cases.update_product_sku import UpdateProductSkuUseCase
from src.application.use_cases.delete_position import DeletePositionUseCase
from src.api.schemas.position_schemas import ReviewActionRequest
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.evidence.entities import Evidence
from src.domain.inventory.entities import Inventory
from src.domain.jobs.entities import Job
from src.domain.positions.entities import Position
from src.domain.reviews.entities import ReviewAction
from src.infrastructure.pipeline.v3_job_executor import RUN_ID

logger = logging.getLogger(__name__)

_MANIFEST_FILENAME = "input_manifest.json"
_NORMALIZED_SUBDIR = "input_photos_normalized"
_HEIC_EXTENSIONS = (".heic", ".heif")

# Simple in-process cache for traceability enrichment to avoid repeatedly loading
# the same hybrid_report.json file for multiple positions from the same job.
# Keyed by entity_uid from detected_summary_json.
#
# Best-effort only:
# - Assumes hybrid_report.json is immutable once written by the pipeline.
# - Lives for the life of the process; bounded to avoid unbounded growth.
_TRACEABILITY_CACHE: Dict[str, Tuple[Optional[str], Optional[str], Optional[str]]] = {}
_TRACEABILITY_REPORTS_LOADED: Set[str] = set()
_MAX_TRACEABILITY_JOBS = 128
_MAX_TRACEABILITY_ENTITIES = 4096


def _maybe_evict_traceability_cache() -> None:
    """Best-effort guard to keep the traceability cache bounded.

    When the number of loaded jobs or cached entities grows beyond a small
    threshold (per-process), the cache is cleared. This keeps memory usage
    bounded while preserving the optimization for the common case where
    only a limited set of jobs are being inspected in one process lifetime.
    """
    if (
        len(_TRACEABILITY_REPORTS_LOADED) > _MAX_TRACEABILITY_JOBS
        or len(_TRACEABILITY_CACHE) > _MAX_TRACEABILITY_ENTITIES
    ):
        _TRACEABILITY_CACHE.clear()
        _TRACEABILITY_REPORTS_LOADED.clear()


def resolve_normalized_asset_path(
    output_dir: Path,
    job_repo: JobRepository,
    aisle_id: str,
    asset_id: str,
) -> Optional[Path]:
    """Resolve the normalized (browser-safe) image path for an asset when the original is HEIC/HEIF."""
    job = job_repo.get_latest_by_target("aisle", aisle_id)
    if job is None:
        return None
    job_id = getattr(job, "id", None)
    if not job_id:
        return None
    run_dir = output_dir / job_id / RUN_ID
    job_dir = run_dir.parent
    manifest_path = job_dir / _MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    photos = manifest.get("photos") or []
    for entry in photos:
        if entry.get("image_id") != asset_id:
            continue
        stored_normalized = entry.get("stored_normalized_filename") or ""
        if not stored_normalized:
            return None
        try:
            safe_filename = validate_relative_path(stored_normalized, "stored_normalized_filename")
        except ValueError:
            return None
        normalized_base = run_dir / _NORMALIZED_SUBDIR
        candidate = normalized_base / safe_filename
        try:
            candidate_resolved = candidate.resolve()
            base_resolved = normalized_base.resolve()
            candidate_resolved.relative_to(base_resolved)
        except (ValueError, OSError):
            return None
        if not candidate_resolved.is_file():
            return None
        return Path(candidate_resolved)
    return None


def review_exception_to_http(e: Exception) -> HTTPException:
    """Map application exceptions from review use cases to HTTP responses."""
    if isinstance(e, InventoryNotFoundError):
        return HTTPException(status_code=404, detail="Inventory not found")
    if isinstance(e, AisleNotFoundError):
        return HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    if isinstance(e, PositionNotFoundError):
        return HTTPException(status_code=404, detail="Position not found or does not belong to this aisle")
    if isinstance(e, ProductNotFoundError):
        return HTTPException(status_code=404, detail="Product not found or does not belong to this position")
    if isinstance(e, PositionDeletedError):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, ValueError):
        return HTTPException(status_code=422, detail=str(e))
    raise e


def handle_confirm(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    confirm_uc: ConfirmPositionUseCase,
) -> None:
    try:
        confirm_uc.execute(inventory_id, aisle_id, position_id)
    except (InventoryNotFoundError, AisleNotFoundError, PositionNotFoundError, ValueError, PositionDeletedError) as e:
        raise review_exception_to_http(e)


def handle_update_quantity(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    update_quantity_uc: UpdateProductQuantityUseCase,
) -> None:
    if body.corrected_quantity is None:
        raise HTTPException(status_code=422, detail="corrected_quantity is required for update_quantity")
    try:
        update_quantity_uc.execute(
            inventory_id,
            aisle_id,
            position_id,
            (body.product_id or "").strip(),
            body.corrected_quantity,
        )
    except (InventoryNotFoundError, AisleNotFoundError, PositionNotFoundError, ProductNotFoundError, ValueError, PositionDeletedError) as e:
        raise review_exception_to_http(e)


def handle_update_sku(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    update_sku_uc: UpdateProductSkuUseCase,
) -> None:
    sku = (body.sku or "").strip() if body.sku is not None else ""
    if not sku:
        raise HTTPException(status_code=422, detail="sku is required for update_sku")
    try:
        update_sku_uc.execute(
            inventory_id,
            aisle_id,
            position_id,
            (body.product_id or "").strip(),
            sku,
            body.description,
        )
    except (InventoryNotFoundError, AisleNotFoundError, PositionNotFoundError, ProductNotFoundError, ValueError, PositionDeletedError) as e:
        raise review_exception_to_http(e)


def handle_delete_position(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    delete_uc: DeletePositionUseCase,
) -> None:
    try:
        delete_uc.execute(inventory_id, aisle_id, position_id)
    except (InventoryNotFoundError, AisleNotFoundError, PositionNotFoundError, PositionDeletedError) as e:
        raise review_exception_to_http(e)


def inventory_to_response(inv: Inventory) -> InventoryResponse:
    return InventoryResponse(
        id=inv.id,
        name=inv.name,
        status=inv.status.value,
        created_at=inv.created_at,
    )


def aisle_to_response(a: Aisle, latest_job: Optional[Job] = None) -> AisleResponse:
    latest = None
    if latest_job is not None:
        latest = AisleJobSummary(
            id=latest_job.id,
            status=latest_job.status.value,
            updated_at=latest_job.updated_at,
            error_message=latest_job.error_message,
        )
    return AisleResponse(
        id=a.id,
        inventory_id=a.inventory_id,
        code=a.code,
        status=a.status.value,
        created_at=a.created_at,
        updated_at=a.updated_at,
        error_code=a.error_code,
        error_message=a.error_message,
        latest_job=latest,
    )


def status_response_from_result(result: AisleProcessingStatusResult) -> AisleStatusResponse:
    job_summary = None
    if result.latest_job is not None:
        j = result.latest_job
        job_summary = JobSummary(
            id=j.id,
            status=j.status.value,
            created_at=j.created_at,
            updated_at=j.updated_at,
            error_message=j.error_message,
        )
    return AisleStatusResponse(
        aisle=aisle_to_response(result.aisle, result.latest_job),
        latest_job=job_summary,
    )


def asset_to_response(asset: SourceAsset) -> SourceAssetResponse:
    return SourceAssetResponse(
        id=asset.id,
        aisle_id=asset.aisle_id,
        type=asset.type.value,
        original_filename=asset.original_filename,
        storage_path=asset.storage_path,
        mime_type=asset.mime_type,
        uploaded_at=asset.uploaded_at,
    )


def _parse_summary_quantity(raw: object) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            v = int(raw)
            return v if v >= 0 else None
        except (TypeError, ValueError):
            return None
    if isinstance(raw, str) and raw.strip():
        try:
            v = int(raw.strip())
            return v if v >= 0 else None
        except (ValueError, TypeError):
            return None
    return None


def _summary_sku_and_quantity_from_position(p: Position) -> tuple[Optional[str], int]:
    """Returns (sku, detected_quantity). detected_quantity is always an int (0 when unresolved)."""
    j = p.detected_summary_json
    if not j or not isinstance(j, dict):
        return None, 0
    sku_raw = j.get("internal_code")
    sku = None
    if sku_raw is not None and isinstance(sku_raw, str) and sku_raw.strip():
        sku = sku_raw.strip()
    if sku is None:
        fallback = (
            j.get("review_display_label")
            or j.get("position_barcode")
            or j.get("pallet_id")
        )
        if fallback is not None and isinstance(fallback, str) and fallback.strip():
            sku = fallback.strip()
    q_raw = j.get("final_quantity") if j.get("final_quantity") is not None else j.get("product_label_quantity")
    qty = _parse_summary_quantity(q_raw)
    return sku, qty if qty is not None else 0


def _enrich_position_traceability_from_report(
    p: Position,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Best-effort enrichment of traceability fields from hybrid_report.json.

    Assumptions:
    - hybrid_report.json is written once per job by the pipeline and treated as immutable
      for the life of the backend process.
    - Missing or invalid reports should not raise; instead, enrichment is skipped.
    - This helper is an internal optimization: if the cache is empty or evicted, behavior
      degrades gracefully to "no enrichment" for that entity.
    """
    summary = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    entity_uid = summary.get("entity_uid") if isinstance(summary.get("entity_uid"), str) else None
    if not entity_uid or "_" not in entity_uid:
        return None, None, None
    # Fast path: cached enrichment for this entity.
    cached = _TRACEABILITY_CACHE.get(entity_uid)
    if cached is not None:
        return cached
    parts = entity_uid.rsplit("_", 1)
    if len(parts) != 2:
        return None, None, None
    job_id, _ = parts
    # If we've already attempted to load this job's report and the entity_uid is
    # still not cached, avoid re-reading the same file.
    if job_id in _TRACEABILITY_REPORTS_LOADED:
        return None, None, None
    try:
        base = Path(load_settings().output_dir)
        report_path = base / job_id / "run" / "hybrid_report.json"
        if not report_path.is_file():
            return None, None, None
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        entities = report.get("entities") or []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            ent_uid = ent.get("entity_uid")
            if not ent_uid or not isinstance(ent_uid, str):
                continue
            sid = ent.get("source_image_id")
            ts = ent.get("traceability_status")
            sof = ent.get("source_image_original_filename")
            normalized: Tuple[Optional[str], Optional[str], Optional[str]] = (
                str(sid).strip() if sid is not None and str(sid).strip() else None,
                str(ts).strip() if ts is not None and str(ts).strip() else None,
                str(sof).strip() if sof is not None and str(sof).strip() else None,
            )
            _TRACEABILITY_CACHE[ent_uid] = normalized
        _TRACEABILITY_REPORTS_LOADED.add(job_id)
        _maybe_evict_traceability_cache()
        return _TRACEABILITY_CACHE.get(entity_uid, (None, None, None))
    except Exception as e:
        logger.debug("Enrich position traceability from report failed (entity_uid=%s): %s", entity_uid, e)
        return None, None, None


def position_to_summary(
    p: Position,
    corrected_quantity: Optional[int] = None,
) -> PositionSummaryResponse:
    sku, detected_quantity = _summary_sku_and_quantity_from_position(p)
    summary_json = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    source_image_id = summary_json.get("source_image_id") or None
    traceability_status = summary_json.get("traceability_status") or None
    source_image_original_filename = summary_json.get("source_image_original_filename") or None
    if summary_json.get("entity_uid") and (
        source_image_id is None or traceability_status is None or source_image_original_filename is None
    ):
        sid_from_report, ts_from_report, sof_from_report = _enrich_position_traceability_from_report(p)
        if source_image_id is None and sid_from_report is not None:
            source_image_id = sid_from_report
        if traceability_status is None and ts_from_report is not None:
            traceability_status = ts_from_report
        if source_image_original_filename is None and sof_from_report is not None:
            source_image_original_filename = sof_from_report
    has_evidence = bool(
        p.primary_evidence_id is not None and str(p.primary_evidence_id).strip() != ""
    )
    response_summary_json = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else None
    return PositionSummaryResponse(
        id=p.id,
        aisle_id=p.aisle_id,
        status=p.status.value,
        confidence=p.confidence,
        needs_review=p.needs_review,
        primary_evidence_id=p.primary_evidence_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
        detected_summary_json=response_summary_json,
        sku=sku,
        detected_quantity=detected_quantity,
        corrected_quantity=corrected_quantity,
        source_image_id=source_image_id,
        traceability_status=traceability_status,
        has_evidence=has_evidence,
        source_image_original_filename=source_image_original_filename,
    )


def evidence_to_response(e: Evidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=e.id,
        entity_type=e.entity_type,
        entity_id=e.entity_id,
        type=e.type.value,
        storage_path=e.storage_path,
        source_asset_id=e.source_asset_id,
        is_primary=e.is_primary,
        frame_index=e.frame_index,
        timestamp_ms=e.timestamp_ms,
        bbox_json=e.bbox_json,
        quality_score=e.quality_score,
    )


def review_to_response(r: ReviewAction) -> ReviewActionResponse:
    return ReviewActionResponse(
        id=r.id,
        position_id=r.position_id,
        action_type=r.action_type.value,
        before_json=r.before_json,
        after_json=r.after_json,
        created_at=r.created_at,
        user_id=r.user_id,
        comment=r.comment,
    )


def heic_extensions() -> tuple[str, ...]:
    return _HEIC_EXTENSIONS


def _reset_traceability_cache_for_tests() -> None:
    """Internal helper to clear the traceability cache.

    Intended for tests or one-off scripts that need to isolate behavior
    across runs. Not used by production code paths.
    """
    _TRACEABILITY_CACHE.clear()
    _TRACEABILITY_REPORTS_LOADED.clear()
