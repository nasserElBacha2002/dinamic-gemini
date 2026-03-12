"""
v3.0 Inventories API — HTTP layer only.

Delegates to application use cases. No business logic here.
Dependencies (repo, clock, use cases) provided by api.dependencies.
"""

from __future__ import annotations

import json
import logging
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.config import load_settings

from src.api.dependencies import (
    get_confirm_position_use_case,
    get_create_aisle_use_case,
    get_create_inventory_use_case,
    get_delete_position_use_case,
    get_get_aisle_processing_status_use_case,
    get_get_inventory_metrics_use_case,
    get_get_inventory_use_case,
    get_get_position_detail_use_case,
    get_list_aisle_assets_use_case,
    get_list_aisle_positions_use_case,
    get_list_aisles_with_status_use_case,
    get_list_inventories_use_case,
    get_start_aisle_processing_use_case,
    get_update_product_quantity_use_case,
    get_update_product_sku_use_case,
    get_upload_aisle_assets_use_case,
)
from src.api.schemas.aisle_schemas import CreateAisleRequest, AisleResponse, AisleJobSummary
from src.api.schemas.asset_schemas import SourceAssetResponse, UploadAisleAssetsResponse
from src.api.schemas.processing_schemas import AisleStatusResponse, JobSummary, ProcessAisleResponse
from src.api.schemas.inventory_schemas import CreateInventoryRequest, InventoryResponse, InventoryMetricsResponse
from src.api.schemas.position_schemas import (
    EvidenceResponse,
    PositionDetailResponse,
    PositionListResponse,
    PositionSummaryResponse,
    ProductRecordResponse,
    ReviewActionRequest,
    ReviewActionResponse,
)
from src.application.errors import (
    ActiveJobExistsError,
    AisleNotFoundError,
    DuplicateAisleCodeError,
    EmptyUploadError,
    InventoryNotFoundError,
    PositionDeletedError,
    PositionNotFoundError,
    ProductNotFoundError,
    UnsupportedAssetTypeError,
)
from src.application.use_cases.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.application.use_cases.get_aisle_processing_status import (
    AisleProcessingStatusResult,
    GetAisleProcessingStatusUseCase,
)
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.get_inventory_metrics import GetInventoryMetricsUseCase
from src.application.use_cases.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.list_aisle_positions import ListAislePositionsCommand, ListAislePositionsUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase
from src.application.use_cases.get_position_detail import GetPositionDetailUseCase
from src.application.use_cases.start_aisle_processing import StartAisleProcessingCommand, StartAisleProcessingUseCase
from src.application.use_cases.upload_aisle_assets import UploadAisleAssetsUseCase, UploadedFile
from src.application.use_cases.confirm_position import ConfirmPositionUseCase
from src.application.use_cases.update_product_quantity import UpdateProductQuantityUseCase
from src.application.use_cases.update_product_sku import UpdateProductSkuUseCase
from src.application.use_cases.delete_position import DeletePositionUseCase
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.evidence.entities import Evidence
from src.domain.inventory.entities import Inventory
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.jobs.entities import Job
from src.domain.reviews.entities import ReviewAction

router = APIRouter(prefix="/api/v3/inventories", tags=["inventories-v3"])

logger = logging.getLogger(__name__)


def _review_exception_to_http(e: Exception) -> HTTPException:
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


def _handle_confirm(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    confirm_uc: ConfirmPositionUseCase,
) -> None:
    try:
        confirm_uc.execute(inventory_id, aisle_id, position_id)
    except (InventoryNotFoundError, AisleNotFoundError, PositionNotFoundError, ValueError, PositionDeletedError) as e:
        raise _review_exception_to_http(e)


def _handle_update_quantity(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    update_quantity_uc: UpdateProductQuantityUseCase,
) -> None:
    product_id = (body.product_id or "").strip()
    if not product_id:
        raise HTTPException(status_code=422, detail="product_id is required for update_quantity")
    if body.corrected_quantity is None:
        raise HTTPException(status_code=422, detail="corrected_quantity is required for update_quantity")
    try:
        update_quantity_uc.execute(inventory_id, aisle_id, position_id, product_id, body.corrected_quantity)
    except (InventoryNotFoundError, AisleNotFoundError, PositionNotFoundError, ProductNotFoundError, ValueError, PositionDeletedError) as e:
        raise _review_exception_to_http(e)


def _handle_update_sku(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    update_sku_uc: UpdateProductSkuUseCase,
) -> None:
    product_id = (body.product_id or "").strip()
    if not product_id:
        raise HTTPException(status_code=422, detail="product_id is required for update_sku")
    sku = (body.sku or "").strip() if body.sku is not None else ""
    if not sku:
        raise HTTPException(status_code=422, detail="sku is required for update_sku")
    try:
        update_sku_uc.execute(inventory_id, aisle_id, position_id, product_id, sku, body.description)
    except (InventoryNotFoundError, AisleNotFoundError, PositionNotFoundError, ProductNotFoundError, ValueError, PositionDeletedError) as e:
        raise _review_exception_to_http(e)


def _handle_delete_position(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    delete_uc: DeletePositionUseCase,
) -> None:
    try:
        delete_uc.execute(inventory_id, aisle_id, position_id)
    except (InventoryNotFoundError, AisleNotFoundError, PositionNotFoundError, PositionDeletedError) as e:
        raise _review_exception_to_http(e)


def _inventory_to_response(inv: Inventory) -> InventoryResponse:
    return InventoryResponse(
        id=inv.id,
        name=inv.name,
        status=inv.status.value,
        created_at=inv.created_at,
    )


def _aisle_to_response(a: Aisle, latest_job: Optional[Job] = None) -> AisleResponse:
    latest = None
    if latest_job is not None:
        latest = AisleJobSummary(
            id=latest_job.id,
            status=latest_job.status.value,
            updated_at=latest_job.updated_at,
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


def _status_response_from_result(result: AisleProcessingStatusResult) -> AisleStatusResponse:
    """Compose status DTO from use-case result; keeps route thin."""
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
        aisle=_aisle_to_response(result.aisle, result.latest_job),
        latest_job=job_summary,
    )


def _asset_to_response(asset: SourceAsset) -> SourceAssetResponse:
    return SourceAssetResponse(
        id=asset.id,
        aisle_id=asset.aisle_id,
        type=asset.type.value,
        original_filename=asset.original_filename,
        storage_path=asset.storage_path,
        mime_type=asset.mime_type,
        uploaded_at=asset.uploaded_at,
    )


def _summary_sku_and_quantity_from_position(p: Position) -> tuple[Optional[str], Optional[int]]:
    """Derive display summary (sku, detected_quantity) from position.detected_summary_json.

    This is a summary-extraction path for list responses only. The authoritative source of
    truth for product data is ProductRecord; we derive from detected_summary_json here to
    avoid loading product records in the list flow. Prefer final_quantity then
    product_label_quantity (same precedence as the pipeline mapper).

    sku: internal_code if present; else review_display_label; else position_barcode; else pallet_id (empty → None).
    pallet_id is always in the summary so existing positions show at least pallet id when internal_code is null.
    """
    j = p.detected_summary_json
    if not j or not isinstance(j, dict):
        return None, None
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
    # Prefer final_quantity (resolved count), then product_label_quantity (raw from pipeline).
    q_raw = j.get("final_quantity") if j.get("final_quantity") is not None else j.get("product_label_quantity")
    qty = _parse_summary_quantity(q_raw)
    # Business rule: always show a counted quantity. When unresolved (both null), use 0 so the frontend never gets null.
    if qty is None:
        qty = 0
    return sku, qty


def _parse_summary_quantity(raw: object) -> Optional[int]:
    """Parse quantity from summary JSON: int/float or numeric string; invalid or negative -> None."""
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


def _enrich_position_traceability_from_report(
    p: Position,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Load source_image_id, traceability_status, source_image_original_filename from hybrid_report.json when position summary is missing them.

    entity_uid format: {job_id}_{model_entity_id}. Returns (source_image_id, traceability_status, source_image_original_filename).
    """
    summary = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    entity_uid = summary.get("entity_uid") if isinstance(summary.get("entity_uid"), str) else None
    if not entity_uid or "_" not in entity_uid:
        return None, None, None
    parts = entity_uid.rsplit("_", 1)
    if len(parts) != 2:
        return None, None, None
    job_id, _model_entity_id = parts
    try:
        base = Path(load_settings().output_dir)
        report_path = base / job_id / "run" / "hybrid_report.json"
        if not report_path.is_file():
            return None, None, None
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        entities = report.get("entities") or []
        for ent in entities:
            if isinstance(ent, dict) and ent.get("entity_uid") == entity_uid:
                sid = ent.get("source_image_id")
                ts = ent.get("traceability_status")
                sof = ent.get("source_image_original_filename")
                return (
                    sid if sid is not None and str(sid).strip() else None,
                    ts if ts is not None and str(ts).strip() else None,
                    sof if sof is not None and str(sof).strip() else None,
                )
        return None, None, None
    except Exception as e:
        logger.debug("Enrich position traceability from report failed (entity_uid=%s): %s", entity_uid, e)
        return None, None, None


def _position_to_summary(p: Position) -> PositionSummaryResponse:
    sku, detected_quantity = _summary_sku_and_quantity_from_position(p)
    summary_json = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    source_image_id = summary_json.get("source_image_id") or None
    traceability_status = summary_json.get("traceability_status") or None
    source_image_original_filename = summary_json.get("source_image_original_filename") or None
    # Fallback: if position was persisted before we stored these in summary, load from report
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
    return PositionSummaryResponse(
        id=p.id,
        aisle_id=p.aisle_id,
        status=p.status.value,
        confidence=p.confidence,
        needs_review=p.needs_review,
        primary_evidence_id=p.primary_evidence_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
        detected_summary_json=p.detected_summary_json,
        sku=sku,
        detected_quantity=detected_quantity,
        source_image_id=source_image_id,
        traceability_status=traceability_status,
        has_evidence=has_evidence,
        source_image_original_filename=source_image_original_filename,
    )


def _product_to_response(pr: ProductRecord) -> ProductRecordResponse:
    return ProductRecordResponse(
        id=pr.id,
        position_id=pr.position_id,
        sku=pr.sku,
        description=pr.description,
        detected_quantity=pr.detected_quantity,
        corrected_quantity=pr.corrected_quantity,
        confidence=pr.confidence,
        created_at=pr.created_at,
        updated_at=pr.updated_at,
    )


def _evidence_to_response(e: Evidence) -> EvidenceResponse:
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


def _review_to_response(r: ReviewAction) -> ReviewActionResponse:
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


@router.post("", response_model=InventoryResponse, status_code=201)
def create_inventory(
    payload: CreateInventoryRequest,
    use_case: CreateInventoryUseCase = Depends(get_create_inventory_use_case),
) -> InventoryResponse:
    """Create a new inventory (v3.0)."""
    inventory = use_case.execute(CreateInventoryCommand(name=payload.name))
    return _inventory_to_response(inventory)


@router.get("", response_model=List[InventoryResponse])
def list_inventories(
    use_case: ListInventoriesUseCase = Depends(get_list_inventories_use_case),
) -> List[InventoryResponse]:
    """List all inventories (v3.0)."""
    inventories = use_case.execute()
    return [_inventory_to_response(inv) for inv in inventories]


@router.get("/{inventory_id}", response_model=InventoryResponse)
def get_inventory(
    inventory_id: str,
    use_case: GetInventoryUseCase = Depends(get_get_inventory_use_case),
) -> InventoryResponse:
    """Get a single inventory by id (v3.0). Returns 404 if not found."""
    try:
        inventory = use_case.execute(inventory_id)
        return _inventory_to_response(inventory)
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")


@router.get("/{inventory_id}/metrics", response_model=InventoryMetricsResponse)
def get_inventory_metrics(
    inventory_id: str,
    use_case: GetInventoryMetricsUseCase = Depends(get_get_inventory_metrics_use_case),
) -> InventoryMetricsResponse:
    """Get canonical inventory metrics (Épica 9, Documento técnico §9.6). Returns 404 if inventory not found."""
    try:
        metrics = use_case.execute(inventory_id)
        return InventoryMetricsResponse(**metrics)
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")


@router.post("/{inventory_id}/aisles", response_model=AisleResponse, status_code=201)
def create_aisle(
    inventory_id: str,
    payload: CreateAisleRequest,
    use_case: CreateAisleUseCase = Depends(get_create_aisle_use_case),
) -> AisleResponse:
    """Create an aisle in an inventory (v3.0). Returns 404 if inventory not found, 409 if code duplicate."""
    try:
        aisle = use_case.execute(CreateAisleCommand(inventory_id=inventory_id, code=payload.code))
        return _aisle_to_response(aisle)
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except DuplicateAisleCodeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{inventory_id}/aisles", response_model=List[AisleResponse])
def list_aisles(
    inventory_id: str,
    use_case: ListAislesWithStatusUseCase = Depends(get_list_aisles_with_status_use_case),
) -> List[AisleResponse]:
    """List aisles for an inventory (v3.0). Returns 404 if inventory not found. Includes latest job per aisle."""
    try:
        items = use_case.execute(inventory_id)
        return [_aisle_to_response(item.aisle, item.latest_job) for item in items]
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")


@router.post("/{inventory_id}/aisles/{aisle_id}/process", response_model=ProcessAisleResponse, status_code=202)
def start_aisle_processing(
    inventory_id: str,
    aisle_id: str,
    use_case: StartAisleProcessingUseCase = Depends(get_start_aisle_processing_use_case),
) -> ProcessAisleResponse:
    try:
        job_id = use_case.execute(StartAisleProcessingCommand(inventory_id=inventory_id, aisle_id=aisle_id))
        return ProcessAisleResponse(job_id=job_id)
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except ActiveJobExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{inventory_id}/aisles/{aisle_id}/status", response_model=AisleStatusResponse)
def get_aisle_status(
    inventory_id: str,
    aisle_id: str,
    use_case: GetAisleProcessingStatusUseCase = Depends(get_get_aisle_processing_status_use_case),
) -> AisleStatusResponse:
    try:
        result = use_case.execute(inventory_id, aisle_id)
        return _status_response_from_result(result)
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/assets",
    response_model=UploadAisleAssetsResponse,
    status_code=201,
)
async def upload_aisle_assets(
    inventory_id: str,
    aisle_id: str,
    files: List[UploadFile] = File(..., description="One or more image or video files"),
    use_case: UploadAisleAssetsUseCase = Depends(get_upload_aisle_assets_use_case),
) -> UploadAisleAssetsResponse:
    """Upload one or more assets (photos/videos) to an aisle. Aisle transitions to assets_uploaded."""
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")
    uploaded: List[UploadedFile] = []
    for u in files:
        if not u.filename and not getattr(u, "content_type", None):
            continue
        content = await u.read()
        uploaded.append(
            UploadedFile(
                original_filename=u.filename or "file",
                file_obj=BytesIO(content),
                content_type=u.content_type or "application/octet-stream",
            )
        )
    if not uploaded:
        raise HTTPException(status_code=422, detail="At least one file is required")
    try:
        created = use_case.execute(inventory_id, aisle_id, uploaded)
        return UploadAisleAssetsResponse(assets=[_asset_to_response(a) for a in created])
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except EmptyUploadError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except UnsupportedAssetTypeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{inventory_id}/aisles/{aisle_id}/assets", response_model=List[SourceAssetResponse])
def list_aisle_assets(
    inventory_id: str,
    aisle_id: str,
    use_case: ListAisleAssetsUseCase = Depends(get_list_aisle_assets_use_case),
) -> List[SourceAssetResponse]:
    """List source assets for an aisle."""
    try:
        assets = use_case.execute(inventory_id, aisle_id)
        return [_asset_to_response(a) for a in assets]
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file",
    response_class=FileResponse,
)
def get_aisle_asset_file(
    inventory_id: str,
    aisle_id: str,
    asset_id: str,
    use_case: ListAisleAssetsUseCase = Depends(get_list_aisle_assets_use_case),
) -> FileResponse:
    """Serve the reference image/file for an aisle asset. Used by Position Detail to open the source image.
    Returns 404 if inventory/aisle/asset not found or file is missing. Safe for position.source_image_id (asset id)."""
    try:
        assets = use_case.execute(inventory_id, aisle_id)
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    asset = next((a for a in assets if a.id == asset_id), None)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    base = Path(load_settings().output_dir) / "v3_uploads"
    file_path = (base / asset.storage_path).resolve()
    try:
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Asset file not found")
        file_path.relative_to(base.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Asset path invalid")
    return FileResponse(
        path=str(file_path),
        media_type=asset.mime_type or "application/octet-stream",
        filename=asset.original_filename or "file",
    )


@router.get("/{inventory_id}/aisles/{aisle_id}/positions", response_model=PositionListResponse)
def list_aisle_positions(
    inventory_id: str,
    aisle_id: str,
    use_case: ListAislePositionsUseCase = Depends(get_list_aisle_positions_use_case),
) -> PositionListResponse:
    """List result positions for an aisle. Response includes summary sku and detected_quantity when available."""
    try:
        positions = use_case.execute(
            ListAislePositionsCommand(inventory_id=inventory_id, aisle_id=aisle_id)
        )
        return PositionListResponse(
            positions=[_position_to_summary(p) for p in positions]
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/positions/{position_id}",
    response_model=PositionDetailResponse,
)
def get_position_detail(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    use_case: GetPositionDetailUseCase = Depends(get_get_position_detail_use_case),
) -> PositionDetailResponse:
    """Get position detail with products and evidences (Épica 6)."""
    try:
        result = use_case.execute(inventory_id, aisle_id, position_id)
        return PositionDetailResponse(
            position=_position_to_summary(result.position),
            products=[_product_to_response(pr) for pr in result.products],
            evidences=[_evidence_to_response(e) for e in result.evidences],
            review_actions=[_review_to_response(ra) for ra in result.review_actions],
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except PositionNotFoundError:
        raise HTTPException(status_code=404, detail="Position not found or does not belong to this aisle")


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/reviews",
    status_code=204,
)
def submit_review_action(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    confirm_uc: ConfirmPositionUseCase = Depends(get_confirm_position_use_case),
    update_quantity_uc: UpdateProductQuantityUseCase = Depends(get_update_product_quantity_use_case),
    update_sku_uc: UpdateProductSkuUseCase = Depends(get_update_product_sku_use_case),
    delete_uc: DeletePositionUseCase = Depends(get_delete_position_use_case),
) -> None:
    """Submit a manual review action (confirm, update_quantity, update_sku, delete_position). Épica 8."""
    if body.action_type == "confirm":
        _handle_confirm(inventory_id, aisle_id, position_id, confirm_uc)
        return
    if body.action_type == "update_quantity":
        _handle_update_quantity(inventory_id, aisle_id, position_id, body, update_quantity_uc)
        return
    if body.action_type == "update_sku":
        _handle_update_sku(inventory_id, aisle_id, position_id, body, update_sku_uc)
        return
    if body.action_type == "delete_position":
        _handle_delete_position(inventory_id, aisle_id, position_id, delete_uc)
        return
