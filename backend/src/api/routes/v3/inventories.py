"""v3 inventory CRUD, metrics, and processing options.

GET / (collection) returns InventoryListItemResponse — screen-ready list rows with aggregates.
GET /{id} and POST / return InventoryResponse (entity without list aggregates).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from src.api.constants.error_wire import HTTP_DETAIL_ONLY_FORMAT_CSV_SUPPORTED
from src.api.dependencies import (
    get_create_inventory_use_case,
    get_export_inventory_package_zip_use_case,
    get_export_inventory_results_use_case,
    get_export_inventory_summary_csv_use_case,
    get_get_inventory_metrics_use_case,
    get_get_inventory_use_case,
    get_list_inventory_list_items_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.inventory_schemas import (
    CreateInventoryRequest,
    InventoryMetricsResponse,
    InventoryResponse,
)
from src.api.schemas.listing_schemas import PaginatedInventoryListResponse, compute_total_pages
from src.api.schemas.processing_schemas import (
    ProcessingModelOption,
    ProcessingPromptOptionItem,
    ProcessingProviderOptionItem,
    ProcessingProviderOptionsResponse,
)
from src.application.errors import ClientNotFoundError, InventoryNotFoundError
from src.application.services.inventory_table_query_params import (
    build_inventory_table_query_from_route_params,
)
from src.application.services.processing_provider_availability import (
    ProcessingOptionsMode,
    build_processing_provider_options_payload,
)
from src.application.use_cases.inventories.create_inventory import (
    CreateInventoryCommand,
    CreateInventoryUseCase,
)
from src.application.use_cases.inventories.export_inventory_business import (
    ExportInventoryPackageZipUseCase,
    ExportInventorySummaryCsvUseCase,
)
from src.application.use_cases.inventories.export_inventory_results import (
    ExportInventoryResultsUseCase,
)
from src.application.use_cases.inventories.get_inventory import GetInventoryUseCase
from src.application.use_cases.inventories.get_inventory_metrics import GetInventoryMetricsUseCase
from src.application.use_cases.inventories.list_inventory_list_items import (
    ListInventoryListItemsUseCase,
)
from src.config import load_settings
from src.domain.inventory.entities import InventoryProcessingMode

from .shared import inventory_list_item_to_response, inventory_to_response

router = APIRouter()


@router.post("/", response_model=InventoryResponse, status_code=201)
def create_inventory(
    payload: CreateInventoryRequest,
    use_case: CreateInventoryUseCase = Depends(get_create_inventory_use_case),
) -> InventoryResponse:
    """Create a new inventory (v3.0)."""
    try:
        mode = InventoryProcessingMode(payload.processing_mode)
        inventory = use_case.execute(
            CreateInventoryCommand(
                name=payload.name,
                processing_mode=mode,
                client_id=payload.client_id,
            )
        )
        return inventory_to_response(inventory)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ClientNotFoundError as e:
        reraise_if_mapped(e)
        raise


@router.get("/", response_model=PaginatedInventoryListResponse)
def list_inventories(
    use_case: ListInventoryListItemsUseCase = Depends(get_list_inventory_list_items_use_case),
    search: str | None = Query(None, description="Case-insensitive substring on inventory name."),
    status: str | None = Query(
        None, description="Exact inventory status (wire value, e.g. draft)."
    ),
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
    q = build_inventory_table_query_from_route_params(
        search=search,
        status=status,
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
def list_processing_provider_options(
    mode: ProcessingOptionsMode = Query(
        "test",
        description=(
            "test — all configured models per provider; "
            "production — only production-ready providers with their default model each."
        ),
    ),
) -> ProcessingProviderOptionsResponse:
    """Selectable pipeline providers, models, and prompt profiles for POST aisle process (Phase 5)."""
    settings = load_settings()
    payload = build_processing_provider_options_payload(settings, mode=mode)
    prompt_items = [
        ProcessingPromptOptionItem(**row) for row in payload["prompt_profiles"]
    ]
    items = [
        ProcessingProviderOptionItem(
            key=row["key"],
            label=row["label"],
            execution_mode=row["execution_mode"],
            description=row.get("description"),
            models=[ProcessingModelOption(**m) for m in row["models"]],
            default_model=row.get("default_model"),
            production_available=row.get("production_available"),
            unavailable_reason=row.get("unavailable_reason"),
            is_default_provider=bool(row.get("is_default_provider")),
        )
        for row in payload["providers"]
    ]
    return ProcessingProviderOptionsResponse(
        mode=payload["mode"],
        default_provider_key=payload["default_provider_key"],
        default_model_key=payload.get("default_model_key"),
        default_prompt_key=payload["default_prompt_key"],
        prompt_profiles=prompt_items,
        providers=items,
    )


@router.get("/{inventory_id}/export/summary")
def export_inventory_summary_csv(
    inventory_id: str,
    level: str = Query(
        "inventory",
        description="Summary level: inventory (one row) or aisles (one row per aisle).",
    ),
    use_case: ExportInventorySummaryCsvUseCase = Depends(get_export_inventory_summary_csv_use_case),
) -> Response:
    """Download inventory or aisle rollup summary CSV (business columns, additive)."""
    lvl = (level or "inventory").strip().lower()
    try:
        if lvl == "aisles":
            body, filename = use_case.execute_aisles_summary_csv(inventory_id)
        elif lvl == "inventory":
            body, filename = use_case.execute_inventory_summary_csv(inventory_id)
        else:
            raise HTTPException(status_code=422, detail="level must be inventory or aisles")
    except HTTPException:
        raise
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{inventory_id}/export/package")
def export_inventory_package_zip(
    inventory_id: str,
    use_case: ExportInventoryPackageZipUseCase = Depends(get_export_inventory_package_zip_use_case),
) -> Response:
    """Download ZIP with inventory summary, aisles summary, and per-aisle business operational CSVs."""
    try:
        zip_bytes, filename = use_case.execute_zip(inventory_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{inventory_id}/export")
def export_inventory_results(
    inventory_id: str,
    export_format: str = Query(
        "csv", alias="format", description="Export format (only csv supported)."
    ),
    technical: bool = Query(
        False,
        description="When true, export the technical snapshot CSV instead of the operational contract CSV.",
    ),
    use_case: ExportInventoryResultsUseCase = Depends(get_export_inventory_results_use_case),
) -> Response:
    """Download consolidated inventory results as CSV (one row per reviewable position after SKU consolidation)."""
    if (export_format or "").strip().lower() != "csv":
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_ONLY_FORMAT_CSV_SUPPORTED)
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
        raise


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
        raise
