"""Job image coverage + manual result creation routes."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from src.api.dependencies import (
    get_create_manual_image_result_use_case,
    get_list_job_image_results_use_case,
)
from src.api.errors.error_mapping import reraise_if_mapped
from src.api.routes.v3.shared import position_to_summary
from src.api.schemas.image_result_schemas import (
    CreateManualImageResultRequest,
    CreateManualImageResultResponse,
    JobImageResultCountersResponse,
    JobImageResultItemResponse,
    JobImageResultsResponse,
)
from src.api.schemas.listing_schemas import compute_total_pages
from src.application.errors import (
    AssetNotInJobSnapshotError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    ManualResultAlreadyExistsError,
    ManualResultNotAllowedForAssetTypeError,
    PhotosJobRequiredError,
    SourceAssetNotFoundForAisleError,
)
from src.application.use_cases.positions.create_manual_image_result import (
    CreateManualImageResultCommand,
    CreateManualImageResultUseCase,
)
from src.application.use_cases.positions.list_job_image_results import (
    ListJobImageResultsCommand,
    ListJobImageResultsUseCase,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser

logger = logging.getLogger(__name__)

router = APIRouter()


def _asset_file_image_url(inventory_id: str, aisle_id: str, source_asset_id: str, job_id: str) -> str:
    """Authenticated file path clients already know how to resolve (Bearer /file)."""
    return (
        f"/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/"
        f"{source_asset_id}/file?job_id={job_id}"
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/image-results",
    response_model=JobImageResultsResponse,
)
def list_job_image_results(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    result_status: Literal["all", "with_result", "without_result"] = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    use_case: ListJobImageResultsUseCase = Depends(get_list_job_image_results_use_case),
) -> JobImageResultsResponse:
    try:
        result = use_case.execute(
            ListJobImageResultsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                result_status=result_status,
                page=page,
                page_size=page_size,
            )
        )
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        PhotosJobRequiredError,
    ) as exc:
        reraise_if_mapped(exc)
        raise

    items: list[JobImageResultItemResponse] = []
    for row in result.items:
        summaries = [
            position_to_summary(
                position,
                corrected_quantity=(
                    product.corrected_quantity if product is not None else None
                ),
                primary_product=product,
                include_technical_snapshot=False,
            )
            for position, product in zip(row.positions, row.primary_products, strict=True)
        ]
        items.append(
            JobImageResultItemResponse(
                image_id=row.image_id,
                source_asset_id=row.source_asset_id,
                job_id=row.job_id,
                image_url=_asset_file_image_url(
                    inventory_id, aisle_id, row.source_asset_id, row.job_id
                ),
                original_filename=row.original_filename,
                created_at=row.created_at,  # type: ignore[arg-type]
                processing_status=row.processing_status,
                has_result=row.has_result,
                result_count=row.result_count,
                results=summaries,
            )
        )

    return JobImageResultsResponse(
        items=items,
        page=result.page,
        page_size=result.page_size,
        total_items=result.total_items,
        total_pages=compute_total_pages(result.total_items, result.page_size),
        counters=JobImageResultCountersResponse(
            total_images=result.counters.total_images,
            with_result=result.counters.with_result,
            without_result=result.counters.without_result,
        ),
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/assets/{source_asset_id}/manual-result",
    response_model=CreateManualImageResultResponse,
    status_code=201,
)
def create_manual_image_result(
    inventory_id: str,
    aisle_id: str,
    source_asset_id: str,
    body: CreateManualImageResultRequest,
    request: Request,
    use_case: CreateManualImageResultUseCase = Depends(get_create_manual_image_result_use_case),
    user: AuthUser = Depends(get_current_admin),
) -> CreateManualImageResultResponse:
    _ = request  # reserved for future audit context
    try:
        outcome = use_case.execute(
            CreateManualImageResultCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                source_asset_id=source_asset_id,
                job_id=body.job_id,
                sku=body.sku,
                quantity=body.quantity,
                description=body.description,
                position_code=body.position_code,
                user_id=user.id,
            )
        )
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        PhotosJobRequiredError,
        AssetNotInJobSnapshotError,
        ManualResultNotAllowedForAssetTypeError,
        SourceAssetNotFoundForAisleError,
        ManualResultAlreadyExistsError,
    ) as exc:
        reraise_if_mapped(exc)
        raise
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc

    summary = position_to_summary(
        outcome.position,
        corrected_quantity=outcome.product.corrected_quantity,
        primary_product=outcome.product,
        include_technical_snapshot=False,
    )
    return CreateManualImageResultResponse(position=summary)
