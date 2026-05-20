"""v3 aisle code scans — QR/barcode auxiliary flow (independent of AI worker)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import (
    get_list_aisle_code_scans_use_case,
    get_run_aisle_code_scan_use_case,
    get_summarize_aisle_code_scans_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.code_scan_schemas import (
    CodeScanBoundingBoxResponse,
    CodeScanDetectionResponse,
    CodeScanRunSummaryResponse,
    CodeScanSummaryItemResponse,
    ListAisleCodeScansResponse,
    RunAisleCodeScanResponse,
    SummarizeAisleCodeScansResponse,
)
from src.application.errors import AisleNotFoundError
from src.application.services.code_scan_run_metadata import warnings_from_run_metadata
from src.application.use_cases.list_aisle_code_scans import ListAisleCodeScansCommand
from src.application.use_cases.run_aisle_code_scan import RunAisleCodeScanCommand
from src.application.use_cases.summarize_aisle_code_scans import SummarizeAisleCodeScansCommand
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.code_scans.bounding_box import parse_bounding_box
from src.domain.code_scans.entities import CodeScanRun

router = APIRouter()


def _run_to_summary(run: CodeScanRun, *, warnings: list[str] | None = None) -> CodeScanRunSummaryResponse:
    merged = list(warnings if warnings is not None else warnings_from_run_metadata(run.metadata_json))
    return CodeScanRunSummaryResponse(
        id=run.id,
        status=run.status.value,
        total_assets=run.total_assets,
        processed_assets=run.processed_assets,
        failed_assets=run.failed_assets,
        total_codes_found=run.total_codes_found,
        total_qr_found=run.total_qr_found,
        total_barcodes_found=run.total_barcodes_found,
        started_at=run.started_at,
        finished_at=run.finished_at,
        scanner_engine=run.scanner_engine,
        error_message=run.error_message,
        warnings=merged,
        metadata_json=run.metadata_json,
    )


def _bbox_to_response(raw: dict | None) -> CodeScanBoundingBoxResponse | None:
    parsed = parse_bounding_box(raw)
    if parsed is None:
        return None
    return CodeScanBoundingBoxResponse.model_validate(parsed)


def _detection_to_response(d) -> CodeScanDetectionResponse:
    return CodeScanDetectionResponse(
        id=d.id,
        run_id=d.run_id,
        asset_id=d.asset_id,
        code_type=d.code_type.value,
        code_value=d.code_value,
        normalized_code_value=d.normalized_code_value,
        detection_status=d.detection_status.value,
        confidence=d.confidence,
        bounding_box_json=_bbox_to_response(d.bounding_box_json),
        scanner_engine=d.scanner_engine,
        created_at=d.created_at,
        metadata_json=d.metadata_json,
        matched_position_id=d.matched_position_id,
        match_status=d.match_status,
        match_type=d.match_type,
        match_confidence=d.match_confidence,
        match_metadata_json=d.match_metadata_json,
        matched_at=d.matched_at,
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/code-scans/run",
    response_model=RunAisleCodeScanResponse,
    status_code=200,
)
def run_aisle_code_scan(
    inventory_id: str,
    aisle_id: str,
    job_id: str | None = Query(
        None,
        description="Result context job id for read-only matching (same as aisle positions list).",
    ),
    current_admin: AuthUser = Depends(get_current_admin),
    use_case=Depends(get_run_aisle_code_scan_use_case),
) -> RunAisleCodeScanResponse:
    """Run a synchronous code scan over uploaded aisle source assets (pyzbar)."""
    try:
        result = use_case.execute(
            RunAisleCodeScanCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                created_by=current_admin.id,
                job_id=job_id,
            )
        )
        return RunAisleCodeScanResponse(
            run=CodeScanRunSummaryResponse(
                id=result.run_id,
                status=result.status.value,
                total_assets=result.total_assets,
                processed_assets=result.processed_assets,
                failed_assets=result.failed_assets,
                total_codes_found=result.total_codes_found,
                total_qr_found=result.total_qr_found,
                total_barcodes_found=result.total_barcodes_found,
                started_at=result.started_at,
                finished_at=result.finished_at,
                scanner_engine=result.scanner_engine,
                error_message=result.error_message,
                warnings=list(result.warnings),
                metadata_json=result.metadata_json,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/code-scans",
    response_model=ListAisleCodeScansResponse,
)
def list_aisle_code_scans(
    inventory_id: str,
    aisle_id: str,
    use_case=Depends(get_list_aisle_code_scans_use_case),
) -> ListAisleCodeScansResponse:
    try:
        result = use_case.execute(
            ListAisleCodeScansCommand(inventory_id=inventory_id, aisle_id=aisle_id)
        )
        latest = _run_to_summary(result.latest_run) if result.latest_run else None
        return ListAisleCodeScansResponse(
            latest_run=latest,
            detections=[_detection_to_response(d) for d in result.detections],
        )
    except AisleNotFoundError as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/code-scans/summary",
    response_model=SummarizeAisleCodeScansResponse,
)
def summarize_aisle_code_scans(
    inventory_id: str,
    aisle_id: str,
    use_case=Depends(get_summarize_aisle_code_scans_use_case),
) -> SummarizeAisleCodeScansResponse:
    try:
        result = use_case.execute(
            SummarizeAisleCodeScansCommand(inventory_id=inventory_id, aisle_id=aisle_id)
        )
        latest = _run_to_summary(result.latest_run) if result.latest_run else None
        return SummarizeAisleCodeScansResponse(
            latest_run=latest,
            items=[
                CodeScanSummaryItemResponse(
                    code_value=item.code_value,
                    normalized_code_value=item.normalized_code_value,
                    code_type=item.code_type,
                    occurrences=item.occurrences,
                    asset_ids=list(item.asset_ids),
                    first_seen_at=item.first_seen_at,
                    match_status=item.match_status,
                    matched_position_ids=list(item.matched_position_ids),
                    match_types=list(item.match_types),
                    match_status_counts=item.match_status_counts,
                )
                for item in result.items
            ],
        )
    except AisleNotFoundError as e:
        reraise_if_mapped(e)
        raise
