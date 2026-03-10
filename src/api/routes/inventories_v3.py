"""
v3.0 Inventories API — HTTP layer only.

Delegates to application use cases. No business logic here.
Dependencies (repo, clock, use cases) provided by api.dependencies.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from src.api.dependencies import (
    get_create_aisle_use_case,
    get_create_inventory_use_case,
    get_get_aisle_processing_status_use_case,
    get_get_inventory_use_case,
    get_get_position_detail_use_case,
    get_list_aisle_assets_use_case,
    get_list_aisle_positions_use_case,
    get_list_aisles_with_status_use_case,
    get_list_inventories_use_case,
    get_start_aisle_processing_use_case,
    get_upload_aisle_assets_use_case,
)
from src.api.schemas.aisle_schemas import CreateAisleRequest, AisleResponse, AisleJobSummary
from src.api.schemas.asset_schemas import SourceAssetResponse, UploadAisleAssetsResponse
from src.api.schemas.processing_schemas import AisleStatusResponse, JobSummary, ProcessAisleResponse
from src.api.schemas.inventory_schemas import CreateInventoryRequest, InventoryResponse
from src.api.schemas.position_schemas import (
    EvidenceResponse,
    PositionDetailResponse,
    PositionListResponse,
    PositionSummaryResponse,
    ProductRecordResponse,
)
from src.application.errors import ActiveJobExistsError, AisleNotFoundError, DuplicateAisleCodeError, EmptyUploadError, InventoryNotFoundError, PositionNotFoundError, UnsupportedAssetTypeError
from src.application.use_cases.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.application.use_cases.get_aisle_processing_status import (
    AisleProcessingStatusResult,
    GetAisleProcessingStatusUseCase,
)
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.list_aisle_positions import ListAislePositionsCommand, ListAislePositionsUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase
from src.application.use_cases.get_position_detail import GetPositionDetailUseCase
from src.application.use_cases.start_aisle_processing import StartAisleProcessingCommand, StartAisleProcessingUseCase
from src.application.use_cases.upload_aisle_assets import UploadAisleAssetsUseCase, UploadedFile
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.evidence.entities import Evidence
from src.domain.inventory.entities import Inventory
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.jobs.entities import Job

router = APIRouter(prefix="/api/v3/inventories", tags=["inventories-v3"])


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
    """
    j = p.detected_summary_json
    if not j or not isinstance(j, dict):
        return None, None
    sku_raw = j.get("internal_code")
    sku = None
    if sku_raw is not None and isinstance(sku_raw, str) and sku_raw.strip():
        sku = sku_raw.strip()
    # Prefer final_quantity (resolved count), then product_label_quantity (raw from pipeline).
    q_raw = j.get("final_quantity") if j.get("final_quantity") is not None else j.get("product_label_quantity")
    qty = _parse_summary_quantity(q_raw)
    return sku, qty


def _parse_summary_quantity(raw: Any) -> Optional[int]:
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


def _position_to_summary(p: Position) -> PositionSummaryResponse:
    sku, detected_quantity = _summary_sku_and_quantity_from_position(p)
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
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except PositionNotFoundError:
        raise HTTPException(status_code=404, detail="Position not found or does not belong to this aisle")
