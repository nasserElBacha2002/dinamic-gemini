"""v3 inventory CRUD, metrics, and visual references.

GET / (collection) returns InventoryListItemResponse — screen-ready list rows with aggregates.
GET /{id} and POST / return InventoryResponse (entity without list aggregates).
"""

from __future__ import annotations

from io import BytesIO
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from src.api.dependencies import (
    get_create_inventory_use_case,
    get_get_inventory_metrics_use_case,
    get_get_inventory_use_case,
    get_list_inventory_list_items_use_case,
    get_list_inventory_visual_references_use_case,
    get_upload_inventory_visual_references_use_case,
)
from src.api.schemas.inventory_schemas import (
    CreateInventoryRequest,
    InventoryListItemResponse,
    InventoryMetricsResponse,
    InventoryResponse,
    InventoryVisualReferenceListResponse,
    InventoryVisualReferenceResponse,
    UploadInventoryVisualReferencesResponse,
)
from src.application.errors import (
    EmptyUploadError,
    InventoryNotFoundError,
    MaxInventoryVisualReferencesExceededError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.get_inventory_metrics import GetInventoryMetricsUseCase
from src.application.use_cases.list_inventory_list_items import ListInventoryListItemsUseCase
from src.application.use_cases.upload_inventory_visual_references import (
    ListInventoryVisualReferencesUseCase,
    UploadInventoryVisualReferencesUseCase,
    UploadedVisualReferenceFile,
)

from .shared import inventory_list_item_to_response, inventory_to_response

router = APIRouter()


async def _to_uploaded_visual_reference_files(files: List[UploadFile]) -> List[UploadedVisualReferenceFile]:
    """Convert request files to use-case DTOs. Fails clearly on invalid or malformed input."""
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")
    result: List[UploadedVisualReferenceFile] = []
    for i, u in enumerate(files):
        has_name = bool(u.filename and u.filename.strip())
        has_type = bool(getattr(u, "content_type", None) and str(u.content_type).strip())
        if not has_name and not has_type:
            raise HTTPException(
                status_code=422,
                detail=f"File at index {i} has no filename and no content type; each part must be a valid file.",
            )
        content = await u.read()
        size = len(content)
        if size <= 0:
            raise HTTPException(status_code=422, detail="Empty or zero-byte files are not allowed")
        result.append(
            UploadedVisualReferenceFile(
                original_filename=(u.filename or "file").strip(),
                file_obj=BytesIO(content),
                content_type=u.content_type or "application/octet-stream",
                size=size,
            )
        )
    if not result:
        raise HTTPException(status_code=422, detail="At least one file is required")
    return result


@router.post("/", response_model=InventoryResponse, status_code=201)
def create_inventory(
    payload: CreateInventoryRequest,
    use_case: CreateInventoryUseCase = Depends(get_create_inventory_use_case),
) -> InventoryResponse:
    """Create a new inventory (v3.0)."""
    inventory = use_case.execute(CreateInventoryCommand(name=payload.name))
    return inventory_to_response(inventory)


@router.get("/", response_model=List[InventoryListItemResponse])
def list_inventories(
    use_case: ListInventoryListItemsUseCase = Depends(get_list_inventory_list_items_use_case),
) -> List[InventoryListItemResponse]:
    """Primary inventories **list** contract: all inventories with table aggregates (Sprint 1.2).

    Response is ``InventoryListItemResponse[]`` — not the thin ``InventoryResponse`` used for
    get-by-id or create.
    """
    items = use_case.execute()
    return [inventory_list_item_to_response(item) for item in items]


@router.get("/{inventory_id}", response_model=InventoryResponse)
def get_inventory(
    inventory_id: str,
    use_case: GetInventoryUseCase = Depends(get_get_inventory_use_case),
) -> InventoryResponse:
    """Get a single inventory by id (v3.0). Returns 404 if not found."""
    try:
        inventory = use_case.execute(inventory_id)
        return inventory_to_response(inventory)
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")


@router.get("/{inventory_id}/metrics", response_model=InventoryMetricsResponse)
def get_inventory_metrics(
    inventory_id: str,
    use_case: GetInventoryMetricsUseCase = Depends(get_get_inventory_metrics_use_case),
) -> InventoryMetricsResponse:
    """Get canonical inventory metrics. Returns 404 if inventory not found."""
    try:
        metrics = use_case.execute(inventory_id)
        return InventoryMetricsResponse(**metrics)
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")


@router.post(
    "/{inventory_id}/visual-references",
    response_model=UploadInventoryVisualReferencesResponse,
    status_code=201,
)
async def upload_inventory_visual_references(
    inventory_id: str,
    files: List[UploadFile] = File(..., description="One or more image files"),
    use_case: UploadInventoryVisualReferencesUseCase = Depends(get_upload_inventory_visual_references_use_case),
) -> UploadInventoryVisualReferencesResponse:
    """Upload one or more visual reference images for an inventory."""
    uploaded = await _to_uploaded_visual_reference_files(files)
    try:
        created = use_case.execute(inventory_id, uploaded)
        return UploadInventoryVisualReferencesResponse(
            items=[
                InventoryVisualReferenceResponse(
                    id=ref.id,
                    inventory_id=ref.inventory_id,
                    filename=ref.filename,
                    mime_type=ref.mime_type,
                    file_size=ref.file_size,
                    created_at=ref.created_at,
                )
                for ref in created
            ]
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except EmptyUploadError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ZeroByteFileError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except UnsupportedAssetTypeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MaxInventoryVisualReferencesExceededError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{inventory_id}/visual-references",
    response_model=InventoryVisualReferenceListResponse,
)
def list_inventory_visual_references(
    inventory_id: str,
    use_case: ListInventoryVisualReferencesUseCase = Depends(get_list_inventory_visual_references_use_case),
) -> InventoryVisualReferenceListResponse:
    """List visual references for an inventory (ordered by created_at ASC, id ASC)."""
    try:
        refs = use_case.execute(inventory_id)
        return InventoryVisualReferenceListResponse(
            items=[
                InventoryVisualReferenceResponse(
                    id=ref.id,
                    inventory_id=ref.inventory_id,
                    filename=ref.filename,
                    mime_type=ref.mime_type,
                    file_size=ref.file_size,
                    created_at=ref.created_at,
                )
                for ref in refs
            ]
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
