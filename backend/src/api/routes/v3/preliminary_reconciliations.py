"""v3 preliminary vs remote reconciliation — diagnostic enqueue + read-only list."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from src.api.dependencies import (
    get_list_preliminary_reconciliations_use_case,
    get_reconcile_preliminary_detections_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.preliminary_reconciliation_schemas import (
    ListPreliminaryReconciliationsResponse,
    PreliminaryReconciliationItem,
    ReconcilePreliminaryDetectionsRequest,
    ReconcilePreliminaryDetectionsResponse,
    ReconciliationMetricsResponse,
)
from src.application.errors import AisleNotFoundError, JobNotFoundError
from src.application.use_cases.aisles.list_preliminary_reconciliations import (
    ListPreliminaryReconciliationsCommand,
    ListPreliminaryReconciliationsUseCase,
)
from src.application.use_cases.aisles.reconcile_preliminary_detections import (
    EnqueueReconciliationCommand,
    ReconciliationDisabledError,
    ReconcilePreliminaryDetectionsUseCase,
)

router = APIRouter()

PRELIMINARY_RECONCILIATION_DISABLED = "PRELIMINARY_RECONCILIATION_DISABLED"


def _item(row) -> PreliminaryReconciliationItem:
    return PreliminaryReconciliationItem(
        id=row.id,
        preliminary_detection_id=row.preliminary_detection_id,
        asset_id=row.asset_id,
        remote_result_id=row.remote_result_id,
        job_id=row.job_id,
        inventory_id=row.inventory_id,
        aisle_id=row.aisle_id,
        client_file_id=row.client_file_id,
        local_status=row.local_status,
        local_internal_code=row.local_internal_code,
        local_quantity=row.local_quantity,
        remote_status=row.remote_status,
        remote_internal_code=row.remote_internal_code,
        remote_quantity=row.remote_quantity,
        outcome=row.outcome,
        not_comparable_reason=row.not_comparable_reason,
        local_parser_version=row.local_parser_version,
        local_detector_version=row.local_detector_version,
        remote_pipeline_version=row.remote_pipeline_version,
        local_detected_at=row.local_detected_at,
        remote_completed_at=row.remote_completed_at,
        compared_at=row.compared_at,
        comparison_version=row.comparison_version,
        reconciliation_status=row.reconciliation_status,
        remote_result_fingerprint=row.remote_result_fingerprint,
        revision=row.revision,
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/reconcile-preliminary-detections",
    response_model=ReconcilePreliminaryDetectionsResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue diagnostic reconciliation for job snapshot (async worker)",
)
def reconcile_preliminary_detections(
    inventory_id: str,
    aisle_id: str,
    body: ReconcilePreliminaryDetectionsRequest,
    use_case: ReconcilePreliminaryDetectionsUseCase = Depends(
        get_reconcile_preliminary_detections_use_case
    ),
) -> ReconcilePreliminaryDetectionsResponse:
    try:
        result = use_case.execute(
            EnqueueReconciliationCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=body.job_id,
                enqueue_limit=body.enqueue_limit,
            )
        )
    except ReconciliationDisabledError as exc:
        raise StructuredApiHttpError(
            404,
            error_code=PRELIMINARY_RECONCILIATION_DISABLED,
            detail="Preliminary reconciliation is not enabled",
        ) from exc
    except AisleNotFoundError as exc:
        reraise_if_mapped(exc)
        raise StructuredApiHttpError(
            404, error_code="AISLE_NOT_FOUND", detail=str(exc)
        ) from exc
    except JobNotFoundError as exc:
        reraise_if_mapped(exc)
        raise StructuredApiHttpError(
            404, error_code="JOB_NOT_FOUND", detail=str(exc)
        ) from exc

    return ReconcilePreliminaryDetectionsResponse(
        accepted=result.accepted,
        batch_id=result.batch_id,
        enqueued=result.enqueued,
        already_terminal=result.already_terminal,
        reconciliation_ids=list(result.reconciliation_ids),
        status="accepted",
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/preliminary-reconciliations",
    response_model=ListPreliminaryReconciliationsResponse,
    summary="List preliminary vs remote reconciliations (read-only diagnostic)",
)
def list_preliminary_reconciliations(
    inventory_id: str,
    aisle_id: str,
    job_id: str | None = Query(default=None),
    preliminary_detection_id: str | None = Query(default=None),
    comparison_version: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    asset_id: str | None = Query(default=None),
    client_file_id: str | None = Query(default=None),
    parser_version: str | None = Query(default=None),
    detector_version: str | None = Query(default=None),
    comparable: bool | None = Query(default=None),
    compared_after: datetime | None = Query(default=None),
    compared_before: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    use_case: ListPreliminaryReconciliationsUseCase = Depends(
        get_list_preliminary_reconciliations_use_case
    ),
) -> ListPreliminaryReconciliationsResponse:
    try:
        result = use_case.execute(
            ListPreliminaryReconciliationsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                preliminary_detection_id=preliminary_detection_id,
                comparison_version=comparison_version,
                outcome=outcome,
                asset_id=asset_id,
                client_file_id=client_file_id,
                parser_version=parser_version,
                detector_version=detector_version,
                comparable_only=comparable,
                compared_after=compared_after,
                compared_before=compared_before,
                limit=limit,
                offset=offset,
            )
        )
    except ReconciliationDisabledError as exc:
        raise StructuredApiHttpError(
            404,
            error_code=PRELIMINARY_RECONCILIATION_DISABLED,
            detail="Preliminary reconciliation is not enabled",
        ) from exc
    except AisleNotFoundError as exc:
        reraise_if_mapped(exc)
        raise StructuredApiHttpError(
            404, error_code="AISLE_NOT_FOUND", detail=str(exc)
        ) from exc

    m = result.metrics
    return ListPreliminaryReconciliationsResponse(
        items=[_item(r) for r in result.items],
        total=result.total,
        metrics=ReconciliationMetricsResponse(
            total_eligible_drafts=m.total_eligible_drafts,
            total_reconciled=m.total_reconciled,
            total_pending=m.total_pending,
            total_not_comparable=m.total_not_comparable,
            mapping_comparable=m.mapping_comparable,
            code_comparable=m.code_comparable,
            quantity_comparable=m.quantity_comparable,
            code_match_count=m.code_match_count,
            code_mismatch_count=m.code_mismatch_count,
            quantity_match_count=m.quantity_match_count,
            quantity_mismatch_count=m.quantity_mismatch_count,
            local_only_count=m.local_only_count,
            remote_only_count=m.remote_only_count,
            ambiguous_count=m.ambiguous_count,
            both_unresolved_count=m.both_unresolved_count,
            comparability_rate=m.comparability_rate,
            server_code_agreement_rate=m.server_code_agreement_rate,
            quantity_agreement_rate=m.quantity_agreement_rate,
            local_only_rate=m.local_only_rate,
            remote_only_rate=m.remote_only_rate,
            ambiguity_rate=m.ambiguity_rate,
            numerator_agreement=m.numerator_agreement,
            denominator_comparable=m.denominator_comparable,
        ),
    )
