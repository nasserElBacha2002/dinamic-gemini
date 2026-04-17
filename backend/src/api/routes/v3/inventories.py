"""v3 inventory CRUD, metrics, and visual references.

GET / (collection) returns InventoryListItemResponse — screen-ready list rows with aggregates.
GET /{id} and POST / return InventoryResponse (entity without list aggregates).
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from src.api.errors import reraise_if_mapped
from src.api.errors.structured_api_http import StructuredApiHttpError, VISUAL_REFERENCE_NOT_FOUND
from src.api.services.v3_stored_artifact_access import (
    StoredArtifactAccessError,
    resolve_visual_reference_file_response,
)
from src.api.dependencies import (
    get_create_inventory_use_case,
    get_artifact_storage,
    get_delete_inventory_visual_reference_use_case,
    get_export_inventory_results_use_case,
    get_get_inventory_metrics_use_case,
    get_get_inventory_use_case,
    get_list_inventory_list_items_use_case,
    get_list_inventory_visual_references_use_case,
    get_replace_inventory_visual_reference_use_case,
    get_upload_inventory_visual_references_use_case,
)
from src.api.schemas.inventory_schemas import (
    CreateInventoryRequest,
    InventoryMetricsResponse,
    InventoryResponse,
    InventoryVisualReferenceListResponse,
    InventoryVisualReferenceResponse,
    UploadInventoryVisualReferencesResponse,
)
from src.api.schemas.processing_schemas import (
    ProcessingModelOption,
    ProcessingPromptOptionItem,
    ProcessingProviderOptionItem,
    ProcessingProviderOptionsResponse,
)
from src.application.services.processing_experiment_catalog import (
    default_model_for_provider,
    default_prompt_key,
    models_for_provider,
    prompt_profile_catalog,
)
from src.api.schemas.listing_schemas import PaginatedInventoryListResponse, compute_total_pages
from src.application.ports.contracts import InventoryTableQuery
from src.application.errors import (
    InventoryNotFoundError,
    InventoryVisualReferenceNotFoundError,
)
from src.application.use_cases.manage_inventory_visual_references import (
    DeleteInventoryVisualReferenceUseCase,
    ReplaceInventoryVisualReferenceUseCase,
)
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.domain.inventory.entities import InventoryProcessingMode
from src.application.use_cases.export_inventory_results import ExportInventoryResultsUseCase
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.get_inventory_metrics import GetInventoryMetricsUseCase
from src.application.use_cases.list_inventory_list_items import ListInventoryListItemsUseCase
from src.application.use_cases.upload_inventory_visual_references import (
    ListInventoryVisualReferencesUseCase,
    UploadInventoryVisualReferencesUseCase,
    UploadedVisualReferenceFile,
)
from src.config import load_settings
from src.pipeline.providers.definitions import PIPELINE_PROVIDER_SPECS
from src.pipeline.provider_keys import normalize_pipeline_provider_key

from .shared import inventory_list_item_to_response, inventory_to_response

logger = logging.getLogger(__name__)

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
    mode = InventoryProcessingMode(payload.processing_mode)
    inventory = use_case.execute(
        CreateInventoryCommand(name=payload.name, processing_mode=mode)
    )
    return inventory_to_response(inventory)


@router.get("/", response_model=PaginatedInventoryListResponse)
def list_inventories(
    use_case: ListInventoryListItemsUseCase = Depends(get_list_inventory_list_items_use_case),
    search: Optional[str] = Query(None, description="Case-insensitive substring on inventory name."),
    status: Optional[str] = Query(None, description="Exact inventory status (wire value, e.g. draft)."),
    sort_by: str = Query(
        "created_at",
        description="name | created_at | updated_at | status | last_activity_at | pending_review_count | aisles_count",
    ),
    sort_dir: str = Query("desc", description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> PaginatedInventoryListResponse:
    """Inventories table: aggregates per row with search, filter, sort, and pagination (Sprint 1.4).

    **Contract:** returns a **paginated object** (`items`, `page`, `page_size`, `total_items`,
    `total_pages`), not a JSON array. This is an intentional breaking change from the pre–1.4 array body.
    """
    q = InventoryTableQuery(
        search=search.strip() if search and search.strip() else None,
        status=status.strip() if status and str(status).strip() else None,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    rows, total = use_case.execute(q)
    ps = q.page_size
    return PaginatedInventoryListResponse(
        items=[inventory_list_item_to_response(item) for item in rows],
        page=q.page,
        page_size=ps,
        total_items=total,
        total_pages=compute_total_pages(total, ps),
    )


@router.get("/processing-provider-options", response_model=ProcessingProviderOptionsResponse)
def list_processing_provider_options() -> ProcessingProviderOptionsResponse:
    """Selectable pipeline providers, models, and prompt profiles for POST aisle process (Phase 5)."""
    settings = load_settings()
    default_key = normalize_pipeline_provider_key(None, settings)
    default_pk = default_prompt_key(settings)
    prompt_items = [
        ProcessingPromptOptionItem(key=k, label=lab, description=desc)
        for k, lab, desc in prompt_profile_catalog()
    ]
    items: List[ProcessingProviderOptionItem] = []
    for spec in sorted(PIPELINE_PROVIDER_SPECS, key=lambda s: s.key):
        key = spec.key
        mode = "native"
        pairs = models_for_provider(key, settings)
        mopts = [ProcessingModelOption(id=m, label=lab) for m, lab in pairs]
        dm = default_model_for_provider(key, settings)
        items.append(
            ProcessingProviderOptionItem(
                key=key,
                label=spec.label,
                execution_mode=mode,
                description=spec.description,
                models=mopts,
                default_model=dm,
            )
        )
    return ProcessingProviderOptionsResponse(
        default_provider_key=default_key,
        default_prompt_key=default_pk,
        prompt_profiles=prompt_items,
        providers=items,
    )


@router.get("/{inventory_id}/export")
def export_inventory_results(
    inventory_id: str,
    export_format: str = Query("csv", alias="format", description="Export format (only csv supported)."),
    technical: bool = Query(
        False,
        description="When true, export the technical snapshot CSV instead of the operational contract CSV.",
    ),
    use_case: ExportInventoryResultsUseCase = Depends(get_export_inventory_results_use_case),
) -> Response:
    """Download consolidated inventory results as CSV (one row per reviewable position after SKU consolidation)."""
    if (export_format or "").strip().lower() != "csv":
        raise HTTPException(status_code=422, detail="Only format=csv is supported")
    try:
        body = use_case.execute_csv(inventory_id, technical=technical)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    suffix = "technical" if technical else "results"
    filename = f"inventory_{inventory_id}_{suffix}.csv"
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{inventory_id}", response_model=InventoryResponse)
def get_inventory(
    inventory_id: str,
    use_case: GetInventoryUseCase = Depends(get_get_inventory_use_case),
) -> InventoryResponse:
    """Get a single inventory by id (v3.0). Returns 404 if not found."""
    try:
        inventory = use_case.execute(inventory_id)
        return inventory_to_response(inventory)
    except InventoryNotFoundError as e:
        reraise_if_mapped(e)


@router.get("/{inventory_id}/metrics", response_model=InventoryMetricsResponse)
def get_inventory_metrics(
    inventory_id: str,
    use_case: GetInventoryMetricsUseCase = Depends(get_get_inventory_metrics_use_case),
) -> InventoryMetricsResponse:
    """Get canonical inventory metrics. Returns 404 if inventory not found."""
    try:
        metrics = use_case.execute(inventory_id)
        return InventoryMetricsResponse(**metrics)
    except InventoryNotFoundError as e:
        reraise_if_mapped(e)


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
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.delete("/{inventory_id}/visual-references/{reference_id}", status_code=204)
def delete_inventory_visual_reference(
    inventory_id: str,
    reference_id: str,
    use_case: DeleteInventoryVisualReferenceUseCase = Depends(get_delete_inventory_visual_reference_use_case),
) -> Response:
    try:
        use_case.execute(inventory_id, reference_id)
    except (InventoryNotFoundError, InventoryVisualReferenceNotFoundError) as e:
        reraise_if_mapped(e)
    return Response(status_code=204)


@router.put(
    "/{inventory_id}/visual-references/{reference_id}",
    response_model=InventoryVisualReferenceResponse,
)
async def replace_inventory_visual_reference(
    inventory_id: str,
    reference_id: str,
    file: UploadFile = File(..., description="Replacement image file"),
    use_case: ReplaceInventoryVisualReferenceUseCase = Depends(get_replace_inventory_visual_reference_use_case),
) -> InventoryVisualReferenceResponse:
    uploaded = await _to_uploaded_visual_reference_files([file])
    try:
        updated = use_case.execute(inventory_id, reference_id, uploaded[0])
        return InventoryVisualReferenceResponse(
            id=updated.id,
            inventory_id=updated.inventory_id,
            filename=updated.filename,
            mime_type=updated.mime_type,
            file_size=updated.file_size,
            created_at=updated.created_at,
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise


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
    except InventoryNotFoundError as e:
        reraise_if_mapped(e)


@router.get("/{inventory_id}/visual-references/{reference_id}/file")
def get_inventory_visual_reference_file(
    inventory_id: str,
    reference_id: str,
    use_case: ListInventoryVisualReferencesUseCase = Depends(get_list_inventory_visual_references_use_case),
    artifact_storage=Depends(get_artifact_storage),
) -> Response:
    """Resolve a visual reference file URL/stream for operators and UI."""
    try:
        refs = use_case.execute(inventory_id)
    except InventoryNotFoundError as e:
        reraise_if_mapped(e)
    ref = next((r for r in refs if r.id == reference_id), None)
    if ref is None:
        raise StructuredApiHttpError(
            404,
            error_code=VISUAL_REFERENCE_NOT_FOUND,
            detail="Visual reference not found",
        )

    try:
        return resolve_visual_reference_file_response(ref, artifact_store=artifact_storage)
    except StoredArtifactAccessError as e:
        logger.warning(
            "Visual reference file resolution failed: inventory_id=%s reference_id=%s reason=%s detail=%s",
            inventory_id,
            reference_id,
            e.reason_code,
            e.detail,
        )
        reraise_if_mapped(e, cause=e)
