"""Phase 4 sequential position reconciliation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_access_principal,
    get_inventory_access_policy,
    get_position_reconciliation_repo,
    get_reconcile_job_positions_use_case,
)
from src.api.schemas.position_reconciliation_schemas import (
    PositionReconciliationDto,
    ProductPositionAssignmentListResponse,
    assignment_to_dto,
    reconciliation_to_dto,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import PositionReconciliationNotReadyError
from src.application.use_cases.position_reconciliation.get_job_position_reconciliation import (
    GetJobPositionReconciliationCommand,
    GetJobPositionReconciliationUseCase,
)
from src.application.use_cases.position_reconciliation.list_job_position_assignments import (
    ListJobPositionAssignmentsCommand,
    ListJobPositionAssignmentsUseCase,
)
from src.application.use_cases.position_reconciliation.reconcile_job_positions import (
    ReconcileJobPositionsCommand,
)
from src.application.use_cases.position_reconciliation.retry_job_position_reconciliation import (
    RetryJobPositionReconciliationUseCase,
)

router = APIRouter()


@router.get(
    "/{inventory_id}/jobs/{job_id}/position-reconciliation",
    response_model=PositionReconciliationDto,
)
def get_job_position_reconciliation(
    inventory_id: str,
    job_id: str,
    principal: AccessPrincipal = Depends(get_access_principal),
    repository=Depends(get_position_reconciliation_repo),
    access_policy=Depends(get_inventory_access_policy),
) -> PositionReconciliationDto:
    row = GetJobPositionReconciliationUseCase(
        repository=repository, access_policy=access_policy
    ).execute(
        GetJobPositionReconciliationCommand(
            inventory_id=inventory_id, job_id=job_id, principal=principal
        )
    )
    if row is None:
        raise PositionReconciliationNotReadyError(f"No active reconciliation for job {job_id}")
    return reconciliation_to_dto(row)


def _list_assignments(
    *,
    inventory_id: str,
    job_id: str,
    principal: AccessPrincipal,
    repository,
    access_policy,
    unassigned_only: bool,
) -> ProductPositionAssignmentListResponse:
    rows = ListJobPositionAssignmentsUseCase(
        repository=repository, access_policy=access_policy
    ).execute(
        ListJobPositionAssignmentsCommand(
            inventory_id=inventory_id,
            job_id=job_id,
            principal=principal,
            unassigned_only=unassigned_only,
        )
    )
    return ProductPositionAssignmentListResponse(items=[assignment_to_dto(row) for row in rows])


@router.get(
    "/{inventory_id}/jobs/{job_id}/position-assignments",
    response_model=ProductPositionAssignmentListResponse,
)
def list_job_position_assignments(
    inventory_id: str,
    job_id: str,
    principal: AccessPrincipal = Depends(get_access_principal),
    repository=Depends(get_position_reconciliation_repo),
    access_policy=Depends(get_inventory_access_policy),
) -> ProductPositionAssignmentListResponse:
    return _list_assignments(
        inventory_id=inventory_id,
        job_id=job_id,
        principal=principal,
        repository=repository,
        access_policy=access_policy,
        unassigned_only=False,
    )


@router.get(
    "/{inventory_id}/jobs/{job_id}/unassigned-results",
    response_model=ProductPositionAssignmentListResponse,
)
def list_job_unassigned_results(
    inventory_id: str,
    job_id: str,
    principal: AccessPrincipal = Depends(get_access_principal),
    repository=Depends(get_position_reconciliation_repo),
    access_policy=Depends(get_inventory_access_policy),
) -> ProductPositionAssignmentListResponse:
    return _list_assignments(
        inventory_id=inventory_id,
        job_id=job_id,
        principal=principal,
        repository=repository,
        access_policy=access_policy,
        unassigned_only=True,
    )


@router.post(
    "/{inventory_id}/jobs/{job_id}/position-reconciliation/retry",
    response_model=PositionReconciliationDto,
)
def retry_job_position_reconciliation(
    inventory_id: str,
    job_id: str,
    principal: AccessPrincipal = Depends(get_access_principal),
    reconcile=Depends(get_reconcile_job_positions_use_case),
) -> PositionReconciliationDto:
    result = RetryJobPositionReconciliationUseCase(reconcile).execute(
        ReconcileJobPositionsCommand(
            inventory_id=inventory_id,
            job_id=job_id,
            principal=principal,
        )
    )
    return reconciliation_to_dto(result.reconciliation)
