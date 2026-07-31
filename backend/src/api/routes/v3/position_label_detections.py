"""Query routes for image position label detections (Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_access_principal,
    get_aisle_repo,
    get_image_position_label_detection_repo,
    get_inventory_access_policy,
    get_inventory_repo,
    get_job_repo,
)
from src.api.schemas.position_label_detection_schemas import (
    ImagePositionDetectionListResponse,
    detection_to_dto,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import StrategyDisabledError
from src.application.use_cases.position_label_detection.list_job_position_detections import (
    ListJobPositionDetectionsCommand,
    ListJobPositionDetectionsUseCase,
)
from src.config import load_settings

router = APIRouter()


def _require_detection_enabled() -> None:
    if not load_settings().position_label_detection_enabled:
        raise StrategyDisabledError("POSITION_LABEL_DETECTION_ENABLED=false")


@router.get(
    "/{inventory_id}/jobs/{job_id}/position-detections",
    response_model=ImagePositionDetectionListResponse,
)
def list_job_position_detections(
    inventory_id: str,
    job_id: str,
    principal: AccessPrincipal = Depends(get_access_principal),
    detection_repo=Depends(get_image_position_label_detection_repo),
    inventory_repo=Depends(get_inventory_repo),
    job_repo=Depends(get_job_repo),
    aisle_repo=Depends(get_aisle_repo),
    access_policy=Depends(get_inventory_access_policy),
) -> ImagePositionDetectionListResponse:
    _require_detection_enabled()
    use_case = ListJobPositionDetectionsUseCase(
        detection_repo=detection_repo,
        inventory_repo=inventory_repo,
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        access_policy=access_policy,
    )
    rows = use_case.execute(
        ListJobPositionDetectionsCommand(
            inventory_id=inventory_id,
            job_id=job_id,
            principal=principal,
        )
    )
    return ImagePositionDetectionListResponse(items=[detection_to_dto(r) for r in rows])


@router.get(
    "/{inventory_id}/jobs/{job_id}/source-assets/{asset_id}/position-detections",
    response_model=ImagePositionDetectionListResponse,
)
def list_asset_position_detections(
    inventory_id: str,
    job_id: str,
    asset_id: str,
    principal: AccessPrincipal = Depends(get_access_principal),
    detection_repo=Depends(get_image_position_label_detection_repo),
    inventory_repo=Depends(get_inventory_repo),
    job_repo=Depends(get_job_repo),
    aisle_repo=Depends(get_aisle_repo),
    access_policy=Depends(get_inventory_access_policy),
) -> ImagePositionDetectionListResponse:
    _require_detection_enabled()
    use_case = ListJobPositionDetectionsUseCase(
        detection_repo=detection_repo,
        inventory_repo=inventory_repo,
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        access_policy=access_policy,
    )
    rows = use_case.execute(
        ListJobPositionDetectionsCommand(
            inventory_id=inventory_id,
            job_id=job_id,
            principal=principal,
            source_asset_id=asset_id,
        )
    )
    return ImagePositionDetectionListResponse(items=[detection_to_dto(r) for r in rows])
