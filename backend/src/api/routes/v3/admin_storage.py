"""Admin-only destructive artifact storage cleanup."""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.constants.route_paths import API_V3_ADMIN_ROUTER_PREFIX
from src.api.dependencies import get_artifact_storage
from src.api.schemas.admin_storage_cleanup_schemas import (
    AdminStorageCleanupRequest,
    AdminStorageCleanupResponse,
    LocalCleanupSectionResponse,
    RemoteCleanupSectionResponse,
)
from src.application.use_cases.admin_storage_cleanup import (
    AdminStorageCleanupError,
    AdminStorageCleanupUseCase,
)
from src.auth.dependencies import require_ai_config_inspection_user
from src.config import load_settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=API_V3_ADMIN_ROUTER_PREFIX,
    tags=["admin-v3"],
    dependencies=[Depends(require_ai_config_inspection_user)],
)


@router.post("/storage/cleanup", response_model=AdminStorageCleanupResponse)
def post_admin_storage_cleanup(
    body: AdminStorageCleanupRequest,
    artifact_storage=Depends(get_artifact_storage),
) -> AdminStorageCleanupResponse:
    """
    Dry-run or delete inventory operational artifacts (allowlisted prefixes only).

    Supplier reference images under ``client_suppliers/`` are never deleted.

    Requires primary administrator principal (same gate as ``/admin/ai-config``).
    """
    settings = load_settings()
    use_case = AdminStorageCleanupUseCase(settings=settings, artifact_store=artifact_storage)
    try:
        result = use_case.execute(
            target=body.target,
            mode=body.mode,
            confirm=body.confirm,
            include_legacy_local=body.include_legacy_local,
            include_pipeline_temp=body.include_pipeline_temp,
        )
    except AdminStorageCleanupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    logger.info(
        "admin_storage_cleanup completed mode=%s target=%s ok=%s remote_found=%s local_found=%s",
        result.mode,
        result.target,
        result.ok,
        result.remote.objects_found,
        result.local.files_found,
    )
    return AdminStorageCleanupResponse(
        ok=result.ok,
        mode=result.mode,
        target=result.target,
        remote=RemoteCleanupSectionResponse.model_validate(asdict(result.remote)),
        local=LocalCleanupSectionResponse.model_validate(asdict(result.local)),
    )
