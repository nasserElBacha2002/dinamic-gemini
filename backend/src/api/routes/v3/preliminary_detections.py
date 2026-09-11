"""v3 mobile preliminary CODE_SCAN draft ingest."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_upsert_preliminary_detection_use_case,
    require_inventory_client_scope,
)
from src.api.errors import reraise_if_mapped
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.preliminary_detection_schemas import (
    PositionAuthoritativeResultV2,
    PreliminaryDetectionUpsertRequest,
    PreliminaryDetectionUpsertResponse,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import AisleNotFoundError
from src.application.use_cases.aisles.upsert_preliminary_detection import (
    PRELIMINARY_ASSET_PENDING,
    PRELIMINARY_IDEMPOTENCY_CONFLICT,
    PRELIMINARY_INGEST_DISABLED,
    PRELIMINARY_VALIDATION_FAILED,
    PositionReferenceEvidenceV2,
    PositionSignatureEvidenceV2,
    PreliminaryDetectionIngestDisabledError,
    UpsertPreliminaryDetectionCommand,
    UpsertPreliminaryDetectionUseCase,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.put(
    "/{inventory_id}/aisles/{aisle_id}/preliminary-detections/{draft_id}",
    response_model=PreliminaryDetectionUpsertResponse,
    summary="Upsert mobile preliminary CODE_SCAN draft",
)
def upsert_preliminary_detection(
    inventory_id: str,
    aisle_id: str,
    draft_id: str,
    body: PreliminaryDetectionUpsertRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: UpsertPreliminaryDetectionUseCase = Depends(
        get_upsert_preliminary_detection_use_case
    ),
) -> PreliminaryDetectionUpsertResponse:
    try:
        result = use_case.execute(
            UpsertPreliminaryDetectionCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                draft_id=draft_id,
                schema_version=body.schema_version,
                capture_session_id=body.capture_session_id,
                capture_photo_id=body.capture_photo_id,
                client_file_id=body.client_file_id,
                asset_id=body.asset_id,
                processing_mode=body.processing_mode,
                status=body.status,
                internal_code=body.internal_code,
                quantity=body.quantity,
                quantity_status=body.quantity_status,
                detected_format=body.detected_format,
                detected_symbology=body.detected_symbology,
                candidate_count=body.candidate_count,
                parser_version=body.parser_version,
                detector_version=body.detector_version,
                prepared_asset_sha256=body.prepared_asset_sha256,
                payload_hash=body.payload_hash,
                processing_ms=body.processing_ms,
                detected_at=body.detected_at,
                principal=principal,
                position_reference=(
                    PositionReferenceEvidenceV2(
                        payload_version=body.position_reference.payload_version,
                        local_recognition_id=body.position_reference.local_recognition_id,
                        raw_code=body.position_reference.raw_code,
                        normalized_code=body.position_reference.normalized_code,
                        remote_position_id=body.position_reference.remote_position_id,
                        remote_position_label_id=body.position_reference.remote_position_label_id,
                        source=body.position_reference.source,
                        profile_id=body.position_reference.profile_id,
                        profile_version=body.position_reference.profile_version,
                        client_supplier_id=body.position_reference.client_supplier_id,
                        signature=PositionSignatureEvidenceV2(
                            present=body.position_reference.signature.present,
                            verification=body.position_reference.signature.verification,
                        ),
                        captured_at=body.position_reference.captured_at,
                    )
                    if body.position_reference is not None
                    else None
                ),
            )
        )
    except PreliminaryDetectionIngestDisabledError as exc:
        raise StructuredApiHttpError(
            404,
            error_code=PRELIMINARY_INGEST_DISABLED,
            detail="Preliminary detection ingest is not enabled",
        ) from exc
    except AisleNotFoundError as exc:
        reraise_if_mapped(exc)
        raise StructuredApiHttpError(
            404,
            error_code="AISLE_NOT_FOUND",
            detail=str(exc),
        ) from exc

    if result.status == "REJECTED":
        raise StructuredApiHttpError(
            422,
            error_code=result.error_code or PRELIMINARY_VALIDATION_FAILED,
            detail=";".join(result.validation_errors) or "Validation failed",
        )
    if result.status == "CONFLICT":
        raise StructuredApiHttpError(
            409,
            error_code=result.error_code or PRELIMINARY_IDEMPOTENCY_CONFLICT,
            detail=(
                f"Idempotency conflict requested={result.requested_draft_id} "
                f"canonical={result.draft_id}"
            ),
        )
    if result.status == "PENDING_ASSET":
        raise StructuredApiHttpError(
            404,
            error_code=result.error_code or PRELIMINARY_ASSET_PENDING,
            detail="Asset not found or not scoped to aisle",
        )

    logger.info(
        "preliminary_detection_received draft_id=%s status=%s duplicate=%s",
        result.draft_id,
        result.status,
        result.duplicate,
    )
    return PreliminaryDetectionUpsertResponse(
        draft_id=result.draft_id,
        requested_draft_id=result.requested_draft_id,
        server_preliminary_id=result.server_preliminary_id,
        status=result.status,
        received_at=result.received_at,
        validation_errors=list(result.validation_errors),
        duplicate=result.duplicate,
        position_result=(
            PositionAuthoritativeResultV2(
                local_recognition_id=result.position_result.local_recognition_id,
                normalized_code=result.position_result.normalized_code,
                remote_position_id=result.position_result.remote_position_id,
                remote_position_label_id=result.position_result.remote_position_label_id,
                status=result.position_result.status,
                error_code=result.position_result.error_code,
                retryable=result.position_result.retryable,
                server_timestamp=result.position_result.server_timestamp,
                reconciliation_revision=result.position_result.reconciliation_revision,
                created=result.position_result.created,
                idempotent_replay=result.position_result.idempotent_replay,
            )
            if result.position_result is not None
            else None
        ),
    )
