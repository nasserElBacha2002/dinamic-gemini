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
from src.application.ports.contracts import PositionListQuery
from src.application.use_cases.list_aisle_positions import ListAislePositionsCommand, ListAislePositionsUseCase
from src.application.use_cases.get_position_detail import GetPositionDetailUseCase

from .shared import (
    position_to_summary,
    evidence_to_response,
    review_to_response,
)

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
    page: int = Query(1, ge=1, description="Page index (1-based). Applied before SKU consolidation."),
    page_size: int = Query(
        25,
        ge=1,
        le=500,
        description="Page size (max 500). Applied before consolidation; use with page for large aisles.",
    ),
) -> PositionListResponse:
    """List result positions for an aisle (Aisle Results table). Optional filters and pagination §9.7."""
    try:
        query = PositionListQuery(
            status=status,
            needs_review=needs_review,
            min_confidence=min_confidence,
            sku_filter=sku_filter.strip() if sku_filter and str(sku_filter).strip() else None,
            page=page,
            page_size=page_size,
        )
        positions = use_case.execute(
            ListAislePositionsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                query=query,
            )
        )
        summaries = []
        for p in positions:
            products = product_record_repo.list_by_position(p.id)
            primary = (
                sorted(products, key=lambda x: (x.created_at, x.id))[0]
                if products else None
            )
            corrected_quantity = (
                primary.corrected_quantity if primary is not None else None
            )
            summaries.append(
                position_to_summary(
                    p,
                    corrected_quantity=corrected_quantity,
                    primary_product=primary,
                )
            )
        return PositionListResponse(positions=summaries)
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
        # Use deterministic "display primary" for corrected_quantity: first product by (created_at, id).
        # GetPositionDetailUseCase returns products from list_by_position (order not guaranteed by port);
        # SQL repo orders by created_at ASC, id ASC; memory repo is unordered — sort here for stability.
        products_sorted = sorted(
            result.products,
            key=lambda p: (p.created_at, p.id),
        )
        primary_product = products_sorted[0] if products_sorted else None
        corrected_quantity = (
            primary_product.corrected_quantity if primary_product is not None else None
        )
        return PositionDetailResponse(
            position=position_to_summary(
                result.position,
                corrected_quantity=corrected_quantity,
                primary_product=primary_product,
            ),
            evidences=[evidence_to_response(e) for e in result.evidences],
            review_actions=[review_to_response(ra) for ra in result.review_actions],
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except PositionNotFoundError:
        raise HTTPException(status_code=404, detail="Position not found or does not belong to this aisle")


