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
    PositionRunContextResponse,
)
from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    PositionNotFoundError,
    PositionResultContextMismatchError,
)
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
    page: int = Query(1, ge=1, description="1-based page index after optional SKU consolidation."),
    page_size: int = Query(
        25,
        ge=1,
        le=500,
        description="Page size after optional SKU consolidation (max 500).",
    ),
    sort_by: str = Query(
        "created_at",
        description=(
            "Post-consolidation sort: created_at | updated_at | confidence | sku | quantity | "
            "photo_sequence (requires unmerged rows — SKU merge is disabled automatically for this sort)"
        ),
    ),
    sort_dir: str = Query("asc", description="asc | desc"),
    consolidate_by_sku: bool = Query(
        True,
        description=(
            "When false, skip SKU merge so list rows stay one-to-one with detections (photo review). "
            "Ignored (treated as false) when sort_by=photo_sequence. Default true preserves legacy "
            "consolidated aisle results."
        ),
    ),
    job_id: Optional[str] = Query(
        None,
        description=(
            "Optional inventory job id. Omitted: operational_job_id if set; else legacy null-job rows "
            "only (job_id IS NULL). Explicit job_id always wins."
        ),
    ),
    include_technical: bool = Query(
        False,
        description="When true, include legacy `detected_summary_json` in list rows for transitional/debug clients.",
    ),
) -> PositionListResponse:
    """List result positions for an aisle (Aisle Results).

    Filters apply to **raw** rows; ``page`` / ``page_size`` / sort apply **after** optional SKU consolidation
    (see ``consolidate_by_sku``).
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
            job_id=job_id.strip() if job_id and str(job_id).strip() else None,
            consolidate_by_sku=consolidate_by_sku,
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
            result_job_id=result.resolved_job_id,
            result_context_source=result.result_context_source,
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except JobDoesNotBelongToAisleError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/positions/{position_id}",
    response_model=PositionDetailResponse,
)
def get_position_detail(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    job_id: Optional[str] = Query(
        None,
        description="Optional; must match resolved result context for this position (Phase 2).",
    ),
    exact_position: bool = Query(
        False,
        description=(
            "When true, return products/evidence for this ``position_id`` only — no redirect to a "
            "SKU-consolidated representative row. Use with photo-accurate aisle review lists."
        ),
    ),
    use_case: GetPositionDetailUseCase = Depends(get_get_position_detail_use_case),
) -> PositionDetailResponse:
    """Get detail for the operator-facing current review entity of a position.

    By default the returned ``position`` block follows the same consolidated representative semantics as
    the aisle results list: when ``position_id`` belongs to an aggregated group, detail resolves the
    representative row. Pass ``exact_position=true`` for one-to-one row/evidence traceability.

    **409 Conflict:** When the position exists but its storage ``job_id`` does not match the resolved
    result slice (explicit query param, then ``aisles.operational_job_id``, then legacy null-job
    rows). This avoids returning another run's data without an explicit ``job_id`` override.
    """
    try:
        result = use_case.execute(
            inventory_id,
            aisle_id,
            position_id,
            explicit_job_id=job_id.strip() if job_id and str(job_id).strip() else None,
            exact_position=exact_position,
        )
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
        rc = result.run_context
        return PositionDetailResponse(
            position=position_to_summary(
                result.position,
                corrected_quantity=corrected_quantity,
                primary_product=primary_product,
                include_technical_snapshot=False,
            ),
            technical_snapshot=technical_snapshot_from_view(view),
            evidences=[evidence_to_response(e) for e in result.evidences],
            review_actions=[review_to_response(ra) for ra in result.review_actions],
            run_context=PositionRunContextResponse(
                job_id=rc.job_id,
                result_context_source=rc.result_context_source,
                resolved_job_id=rc.resolved_job_id,
                provider_name=rc.provider_name,
                model_name=rc.model_name,
                prompt_key=rc.prompt_key,
                prompt_version=rc.prompt_version,
            ),
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except PositionNotFoundError:
        raise HTTPException(status_code=404, detail="Position not found or does not belong to this aisle")
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except JobDoesNotBelongToAisleError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PositionResultContextMismatchError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


