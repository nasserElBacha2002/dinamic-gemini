"""v3 read-only operational configuration (currently: upload limits)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

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


class ExtractionProfileCapabilitiesResponse(BaseModel):
    client_extraction_profiles_enabled: bool = Field(...)
    profile_aware_validation_enabled: bool = Field(...)
    reference_template_annotations_enabled: bool = Field(...)


@router.get("/upload-limits", response_model=UploadLimitsResponse)
def get_upload_limits() -> UploadLimitsResponse:
    """Server-enforced upload caps plus advisory client concurrency/retry hints.

    Lets clients (e.g. frontend bulk upload) size batches without hardcoding limits that
    already live in :class:`src.env_settings.grouped_settings.LimitsAndSchemaSettings`.

    ``retry_attempts`` is the number of **additional** retries after the first attempt
    (matching ``UPLOAD_RETRY_ATTEMPTS``).
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


@router.get(
    "/extraction-profile-capabilities",
    response_model=ExtractionProfileCapabilitiesResponse,
)
def get_extraction_profile_capabilities() -> ExtractionProfileCapabilitiesResponse:
    """Real feature-flag capabilities for Phase 6 supplier extraction profiles."""
    settings = load_settings()
    return ExtractionProfileCapabilitiesResponse(
        client_extraction_profiles_enabled=bool(
            getattr(settings, "client_extraction_profiles_enabled", False)
        ),
        profile_aware_validation_enabled=bool(
            getattr(settings, "profile_aware_validation_enabled", False)
        ),
        reference_template_annotations_enabled=bool(
            getattr(settings, "reference_template_annotations_enabled", False)
        ),
    )


class ProcessingObservabilityCapabilitiesResponse(BaseModel):
    processing_observability_enabled: bool = Field(...)
    processing_asset_logs_ui_enabled: bool = False
    processing_asset_reprocess_enabled: bool = False
    processing_manual_actions_enabled: bool = False
    processing_events_persistence_enabled: bool = False


@router.get(
    "/processing-observability-capabilities",
    response_model=ProcessingObservabilityCapabilitiesResponse,
)
def get_processing_observability_capabilities() -> ProcessingObservabilityCapabilitiesResponse:
    """Phase 7 feature-flag capabilities for operational processing UX."""
    settings = load_settings()
    return ProcessingObservabilityCapabilitiesResponse(
        processing_observability_enabled=bool(
            getattr(settings, "processing_observability_enabled", False)
        ),
        processing_asset_logs_ui_enabled=bool(
            getattr(settings, "processing_asset_logs_ui_enabled", False)
        ),
        processing_asset_reprocess_enabled=bool(
            getattr(settings, "processing_asset_reprocess_enabled", False)
        ),
        processing_manual_actions_enabled=bool(
            getattr(settings, "processing_manual_actions_enabled", False)
        ),
        processing_events_persistence_enabled=bool(
            getattr(settings, "processing_events_persistence_enabled", False)
        ),
    )
