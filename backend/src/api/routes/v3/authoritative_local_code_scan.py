"""v3 authoritative local CODE_SCAN — operator-confirmed final results."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from src.api.dependencies import get_persist_authoritative_local_code_scan_use_case
from src.api.errors import reraise_if_mapped
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.authoritative_local_code_scan_schemas import (
    AuthoritativeLocalCodeScanRequest,
    AuthoritativeLocalCodeScanResponse,
)
from src.application.errors import AisleNotFoundError
from src.application.use_cases.aisles.persist_authoritative_local_code_scan import (
    AUTH_ASSET_MISMATCH,
    AUTH_CLIENT_FILE_MISMATCH,
    AUTH_FORBIDDEN,
    AUTH_IDEMPOTENCY_CONFLICT,
    AUTH_INGEST_DISABLED,
    AUTH_VALIDATION_FAILED,
    AuthoritativeIngestDisabledError,
    PersistAuthoritativeLocalCodeScanCommand,
    PersistAuthoritativeLocalCodeScanResultUseCase,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.put(
    "/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-code-scan",
    response_model=AuthoritativeLocalCodeScanResponse,
    summary="Upsert operator-confirmed local CODE_SCAN as authoritative",
)
def put_authoritative_local_code_scan(
    inventory_id: str,
    aisle_id: str,
    asset_id: str,
    body: AuthoritativeLocalCodeScanRequest,
    use_case: PersistAuthoritativeLocalCodeScanResultUseCase = Depends(
        get_persist_authoritative_local_code_scan_use_case
    ),
) -> AuthoritativeLocalCodeScanResponse:
    try:
        result = use_case.execute(
            PersistAuthoritativeLocalCodeScanCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                asset_id=asset_id,
                result_id=body.result_id,
                schema_version=body.schema_version,
                client_file_id=body.client_file_id,
                internal_code=body.internal_code,
                quantity=body.quantity,
                quantity_status=body.quantity_status,
                source=body.source,
                detected_internal_code=body.detected_internal_code,
                detected_quantity=body.detected_quantity,
                detected_symbology=body.detected_symbology,
                parser_version=body.parser_version,
                detector_version=body.detector_version,
                prepared_asset_sha256=body.prepared_asset_sha256,
                confirmed_at=body.confirmed_at,
                confirmed_by_user_id=None,  # never trust client
            )
        )
    except AuthoritativeIngestDisabledError as exc:
        raise StructuredApiHttpError(
            404,
            error_code=AUTH_INGEST_DISABLED,
            detail="Authoritative local CODE_SCAN ingest is not enabled",
        ) from exc
    except AisleNotFoundError as exc:
        reraise_if_mapped(exc)
        raise StructuredApiHttpError(
            404,
            error_code="AISLE_NOT_FOUND",
            detail=str(exc),
        ) from exc

    if result.status == "REJECTED":
        code = result.error_code or AUTH_VALIDATION_FAILED
        status = 403 if code == AUTH_FORBIDDEN else 422
        if code in {AUTH_ASSET_MISMATCH, AUTH_CLIENT_FILE_MISMATCH}:
            status = 404 if code == AUTH_ASSET_MISMATCH else 409
        raise StructuredApiHttpError(
            status,
            error_code=code,
            detail=";".join(result.validation_errors) or "Validation failed",
        )
    if result.status == "CONFLICT":
        raise StructuredApiHttpError(
            409,
            error_code=result.error_code or AUTH_IDEMPOTENCY_CONFLICT,
            detail="Idempotency conflict for authoritative local CODE_SCAN result",
        )

    return AuthoritativeLocalCodeScanResponse(
        result_id=result.result_id,
        asset_id=result.asset_id,
        result_version=result.result_version,
        is_current=result.is_current,
        supersedes_result_id=result.supersedes_result_id,
        status=result.status,
        duplicate=result.duplicate,
        applied_at=result.applied_at,
    )
