"""v3 aisle positions: list, detail."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import (
    get_list_aisle_positions_use_case,
    get_get_position_detail_use_case,
    get_product_record_repo,
)
from src.application.ports.repositories import ProductRecordRepository
from src.api.schemas.position_schemas import (
    EvidenceResponse,
    PositionDetailResponse,
    PositionListResponse,
)
from src.application.errors import AisleNotFoundError, InventoryNotFoundError, PositionNotFoundError
from src.api.schemas.listing_schemas import compute_total_pages
from src.application.services.display_primary_product import select_display_primary_product
from src.application.use_cases.list_aisle_positions import ListAislePositionsCommand, ListAislePositionsUseCase
from src.application.use_cases.get_position_detail import GetPositionDetailUseCase

from .shared import (
    position_to_summary,
    technical_snapshot_from_view,
    evidence_to_response,
    review_to_response,
)
from src.application.mappers.position_canonical_view import build_position_canonical_view

router = APIRouter()


@router.get("/{inventory_id}/aisles/{aisle_id}/positions", response_model=PositionListResponse)
def list_aisle_positions(
    inventory_id: str,
    aisle_id: str,
    use_case: ListAislePositionsUseCase = Depends(get_list_aisle_positions_use_case),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    status: Optional[str] = Query(None, description="Filter by position status (e.g. detected, reviewed)."),
    needs_review: Optional[bool] = Query(None, description="When set, only positions with this needs_review flag."),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum confidence (inclusive)."),
    sku_filter: Optional[str] = Query(None, description="Substring match against product SKU for this aisle."),
    page: int = Query(1, ge=1, description="1-based page index after SKU consolidation."),
    page_size: int = Query(
        25,
        ge=1,
        le=500,
        description="Page size after consolidation (max 500).",
    ),
    sort_by: str = Query(
        "created_at",
        description="Post-consolidation sort: created_at | updated_at | confidence | sku | quantity",
    ),
    sort_dir: str = Query("asc", description="asc | desc"),
    include_technical: bool = Query(
        False,
        description="When true, include legacy `detected_summary_json` in list rows for transitional/debug clients.",
    ),
) -> PositionListResponse:
    """List result positions for an aisle (Aisle Results).

    Filters apply to **raw** rows; ``page`` / ``page_size`` / sort apply **after** SKU consolidation.
    When ``raw_fetch_truncated`` is true in the response, ``total_items`` / ``total_pages`` are only
    reliable within the raw rows the server loaded — not for the entire aisle. See schema docstring.
    """
    try:
        cmd = ListAislePositionsCommand(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            status=status,
            needs_review=needs_review,
            min_confidence=min_confidence,
            sku_filter=sku_filter.strip() if sku_filter and str(sku_filter).strip() else None,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        result = use_case.execute(cmd)
        summaries = []
        for p in result.positions:
            products = product_record_repo.list_by_position(p.id)
            primary = select_display_primary_product(products)
            corrected_quantity = (
                primary.corrected_quantity if primary is not None else None
            )
            summaries.append(
                position_to_summary(
                    p,
                    corrected_quantity=corrected_quantity,
                    primary_product=primary,
                    include_technical_snapshot=include_technical,
                )
            )
        return PositionListResponse(
            positions=summaries,
            page=result.page,
            page_size=result.page_size,
            total_items=result.total_items,
            total_pages=compute_total_pages(result.total_items, result.page_size),
            raw_fetch_truncated=result.raw_fetch_truncated,
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
    """Get position detail with evidences and review history (Épica 6)."""
    try:
        result = use_case.execute(inventory_id, aisle_id, position_id)
        # GetPositionDetailUseCase returns products from list_by_position (order not guaranteed by port);
        # SQL repo orders by created_at ASC, id ASC; memory repo is unordered — use shared display-primary rule.
        primary_product = select_display_primary_product(result.products)
        corrected_quantity = (
            primary_product.corrected_quantity if primary_product is not None else None
        )
        view = build_position_canonical_view(
            result.position,
            primary_product,
            corrected_quantity=corrected_quantity,
        )
        return PositionDetailResponse(
            position=position_to_summary(
                result.position,
                corrected_quantity=corrected_quantity,
                primary_product=primary_product,
                include_technical_snapshot=True,
            ),
            technical_snapshot=technical_snapshot_from_view(view),
            evidences=[evidence_to_response(e) for e in result.evidences],
            review_actions=[review_to_response(ra) for ra in result.review_actions],
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except PositionNotFoundError:
        raise HTTPException(status_code=404, detail="Position not found or does not belong to this aisle")


