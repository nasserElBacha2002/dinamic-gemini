"""v3 read-only operational configuration (currently: upload limits)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.constants.route_paths import API_V3_CONFIG_ROUTER_PREFIX
from src.api.schemas.upload_limits_schemas import UploadLimitsResponse
from src.application.services.upload_request_limits import UploadRequestLimitPolicy
from src.auth.dependencies import get_current_admin
from src.config import load_settings

router = APIRouter(
    prefix=API_V3_CONFIG_ROUTER_PREFIX,
    tags=["config-v3"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/upload-limits", response_model=UploadLimitsResponse)
def get_upload_limits() -> UploadLimitsResponse:
    """Server-enforced upload caps plus advisory client concurrency/retry hints.

    Lets clients (e.g. frontend bulk upload) size batches without hardcoding limits that
    already live in :class:`src.env_settings.grouped_settings.LimitsAndSchemaSettings`.
    """
    settings = load_settings()
    policy = UploadRequestLimitPolicy.from_settings(settings)
    return UploadLimitsResponse(
        max_files_per_request=policy.max_files_per_request,
        max_file_size_bytes=policy.max_file_size_bytes,
        max_request_size_bytes=policy.max_request_size_bytes,
        upload_batch_concurrency=settings.upload_batch_concurrency,
        retry_attempts=settings.upload_retry_attempts,
        retry_base_delay_ms=settings.upload_retry_base_delay_ms,
    )
