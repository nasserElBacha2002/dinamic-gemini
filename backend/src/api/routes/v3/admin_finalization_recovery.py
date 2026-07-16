"""Admin-only targeted finalization recovery — Phase 3.4."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.constants.route_paths import API_V3_ADMIN_ROUTER_PREFIX
from src.api.schemas.admin_finalization_recovery_schemas import (
    AdminFinalizationRecoveryRequest,
    AdminFinalizationRecoveryResponse,
)
from src.application.services.observability_access import CAP_FINALIZATION_RECOVERY
from src.application.use_cases.finalization_recovery.recovery_command import RecoveryCommand
from src.application.use_cases.finalization_recovery.resume_job_finalization import (
    FinalizationRecoveryCoordinator,
)
from src.auth.dependencies import require_observability_capability
from src.auth.schemas import AuthUser
from src.domain.jobs.finalization_recovery import RecoveryOperation, RecoveryResult
from src.runtime.v3_deps import get_finalization_recovery_coordinator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=API_V3_ADMIN_ROUTER_PREFIX,
    tags=["admin-v3"],
)

_OPERATION_MAP = {
    "verify": RecoveryOperation.VERIFY,
    "republish_artifacts": RecoveryOperation.REPUBLISH_ARTIFACTS,
    "terminalize": RecoveryOperation.TERMINALIZE,
    "promote": RecoveryOperation.PROMOTE,
    "reconcile_aisle": RecoveryOperation.RECONCILE_AISLE,
    "reconcile_inventory": RecoveryOperation.RECONCILE_INVENTORY,
    "resume": RecoveryOperation.RESUME,
}


def _to_response(result: RecoveryResult) -> AdminFinalizationRecoveryResponse:
    return AdminFinalizationRecoveryResponse(
        job_id=result.job_id,
        operation=result.operation.value,
        outcome=result.outcome.value,
        dry_run=result.dry_run,
        recovery_id=result.recovery_id,
        error_code=result.error_code,
        sanitized_message=result.sanitized_message,
        previous_assessment_outcome=result.previous_assessment.outcome.value,
        new_assessment_outcome=result.new_assessment.outcome.value,
        eligible_operations=[op.value for op in result.eligible_operations],
        blocked_operations=[op.value for op in result.blocked_operations],
        stages_attempted=[stage.value for stage in result.stages_attempted],
        stages_completed=[stage.value for stage in result.stages_completed],
        stages_skipped=[stage.value for stage in result.stages_skipped],
    )


@router.post("/jobs/{job_id}/finalization/recover", response_model=AdminFinalizationRecoveryResponse)
def post_admin_finalization_recover(
    job_id: str,
    body: AdminFinalizationRecoveryRequest,
    admin: AuthUser = Depends(require_observability_capability(CAP_FINALIZATION_RECOVERY)),
    coordinator: FinalizationRecoveryCoordinator = Depends(get_finalization_recovery_coordinator),
) -> AdminFinalizationRecoveryResponse:
    operation = _OPERATION_MAP.get(body.operation.strip().lower())
    if operation is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported recovery operation: {body.operation}",
        )
    command = RecoveryCommand(
        job_id=job_id,
        dry_run=body.dry_run,
        requested_by=admin.username,
        source="admin_api",
        allow_canceled_terminalization=body.allow_canceled_terminalization,
        include_optional_artifacts=body.include_optional_artifacts,
    )
    result = coordinator.execute(operation, command)
    logger.info(
        "admin_finalization_recovery job_id=%s operation=%s outcome=%s dry_run=%s admin=%s",
        job_id,
        operation.value,
        result.outcome.value,
        body.dry_run,
        admin.username,
    )
    return _to_response(result)
