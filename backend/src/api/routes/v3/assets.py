"""v3 aisle assets: upload, list, file serving."""

from __future__ import annotations

import logging
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from src.config import load_settings
from src.api.dependencies import (
    get_artifact_storage,
    get_list_aisle_assets_use_case,
    get_upload_aisle_assets_use_case,
    get_job_repo,
)
from src.api.services.v3_stored_artifact_access import (
    StoredArtifactAccessError,
    resolve_source_asset_file_response,
    resolve_source_asset_image_display,
)
from src.api.schemas.asset_schemas import (
    SourceAssetImageDisplayUrlResponse,
    SourceAssetResponse,
    UploadAisleAssetsResponse,
)
from src.application.ports.repositories import JobRepository
from src.application.errors import AisleNotFoundError, EmptyUploadError, UnsupportedAssetTypeError
from src.application.use_cases.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.upload_aisle_assets import UploadAisleAssetsUseCase, UploadedFile
from src.domain.assets.entities import SourceAsset

from .shared import asset_to_response, resolve_normalized_asset_path, heic_extensions

logger = logging.getLogger(__name__)
router = APIRouter()


class AssetFileFailureReason(str, Enum):
    """Internal reason for asset file endpoint returning 404 or failure. Used for logging and observability."""
    AISLE_NOT_FOUND = "aisle_not_found"
    ASSET_NOT_FOUND = "asset_not_found"
    FILE_NOT_FOUND = "file_not_found"
    PATH_INVALID = "path_invalid"
    HEIC_PREVIEW_UNAVAILABLE = "heic_preview_unavailable"


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/assets",
    response_model=UploadAisleAssetsResponse,
    status_code=201,
)
async def upload_aisle_assets(
    inventory_id: str,
    aisle_id: str,
    files: List[UploadFile] = File(..., description="One or more image or video files"),
    use_case: UploadAisleAssetsUseCase = Depends(get_upload_aisle_assets_use_case),
) -> UploadAisleAssetsResponse:
    """Upload one or more assets (photos/videos) to an aisle. Aisle transitions to assets_uploaded."""
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")
    uploaded: List[UploadedFile] = []
    for u in files:
        if not u.filename and not getattr(u, "content_type", None):
            continue
        content = await u.read()
        uploaded.append(
            UploadedFile(
                original_filename=u.filename or "file",
                file_obj=BytesIO(content),
                content_type=u.content_type or "application/octet-stream",
            )
        )
    if not uploaded:
        raise HTTPException(status_code=422, detail="At least one file is required")
    try:
        created = use_case.execute(inventory_id, aisle_id, uploaded)
        return UploadAisleAssetsResponse(assets=[asset_to_response(a) for a in created])
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except EmptyUploadError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except UnsupportedAssetTypeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{inventory_id}/aisles/{aisle_id}/assets", response_model=List[SourceAssetResponse])
def list_aisle_assets(
    inventory_id: str,
    aisle_id: str,
    use_case: ListAisleAssetsUseCase = Depends(get_list_aisle_assets_use_case),
) -> List[SourceAssetResponse]:
    """List source assets for an aisle."""
    try:
        assets = use_case.execute(inventory_id, aisle_id)
        return [asset_to_response(a) for a in assets]
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file",
    response_model=None,
    response_class=FileResponse,
)
def get_aisle_asset_file(
    inventory_id: str,
    aisle_id: str,
    asset_id: str,
    job_id: Optional[str] = Query(None, description="Optional job id to resolve HEIC normalized preview from that run"),
    use_case: ListAisleAssetsUseCase = Depends(get_list_aisle_assets_use_case),
    job_repo: JobRepository = Depends(get_job_repo),
    artifact_storage=Depends(get_artifact_storage),
) -> Union[FileResponse, RedirectResponse]:
    """Serve the reference image/file for an aisle asset. HEIC/HEIF: serves normalized JPG when available (optional job_id)."""
    failure_reason: Optional[AssetFileFailureReason] = None
    try:
        assets = use_case.execute(inventory_id, aisle_id)
    except AisleNotFoundError:
        failure_reason = AssetFileFailureReason.AISLE_NOT_FOUND
        logger.warning(
            "Asset file: %s inventory_id=%s aisle_id=%s asset_id=%s",
            failure_reason.value,
            inventory_id,
            aisle_id,
            asset_id,
        )
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    asset = next((a for a in assets if a.id == asset_id), None)
    if asset is None:
        failure_reason = AssetFileFailureReason.ASSET_NOT_FOUND
        logger.warning(
            "Asset file: %s inventory_id=%s aisle_id=%s asset_id=%s",
            failure_reason.value,
            inventory_id,
            aisle_id,
            asset_id,
        )
        raise HTTPException(status_code=404, detail="Asset not found")

    def _asset_is_heic(a: SourceAsset) -> bool:
        mt = (a.mime_type or "").lower()
        if mt in ("image/heic", "image/heif"):
            return True
        if Path(a.storage_path or "").suffix.lower() in heic_extensions():
            return True
        if Path(a.original_filename or "").suffix.lower() in heic_extensions():
            return True
        return False

    # HEIC/HEIF: serve normalized JPEG from local pipeline output when available (unchanged contract).
    if _asset_is_heic(asset):
        output_dir = Path(load_settings().output_dir)
        request_job_id = job_id.strip() if job_id and job_id.strip() else None
        logger.debug(
            "Asset file: HEIC resolving normalized path asset_id=%s job_id=%s",
            asset_id,
            request_job_id,
        )
        normalized_path = resolve_normalized_asset_path(
            output_dir, job_repo, aisle_id, asset_id, job_id=job_id
        )
        if normalized_path is not None:
            preview_filename = (asset.original_filename or "preview").rsplit(".", 1)[0] + ".jpg"
            return FileResponse(
                path=str(normalized_path),
                media_type="image/jpeg",
                filename=preview_filename,
            )
        failure_reason = AssetFileFailureReason.HEIC_PREVIEW_UNAVAILABLE
        logger.warning(
            "Asset file: %s asset_id=%s request_job_id=%s",
            failure_reason.value,
            asset_id,
            request_job_id,
        )
        raise HTTPException(
            status_code=404,
            detail="Preview is not available for this image",
        )

    try:
        return resolve_source_asset_file_response(asset, artifact_store=artifact_storage)
    except StoredArtifactAccessError as e:
        logger.warning(
            "Asset file resolution failed: %s asset_id=%s reason=%s",
            e.reason_code,
            asset_id,
            e.detail,
        )
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url",
    response_model=SourceAssetImageDisplayUrlResponse,
)
def get_aisle_asset_image_display_url(
    inventory_id: str,
    aisle_id: str,
    asset_id: str,
    job_id: Optional[str] = Query(
        None,
        description="Optional job id to align HEIC preview behavior with the /file endpoint",
    ),
    use_case: ListAisleAssetsUseCase = Depends(get_list_aisle_assets_use_case),
    job_repo: JobRepository = Depends(get_job_repo),
    artifact_storage=Depends(get_artifact_storage),
) -> SourceAssetImageDisplayUrlResponse:
    """Return a display strategy for an aisle asset image (presigned URL or authenticated /file fetch)."""
    try:
        assets = use_case.execute(inventory_id, aisle_id)
    except AisleNotFoundError:
        logger.warning(
            "Asset image-display-url: aisle_not_found inventory_id=%s aisle_id=%s asset_id=%s",
            inventory_id,
            aisle_id,
            asset_id,
        )
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    asset = next((a for a in assets if a.id == asset_id), None)
    if asset is None:
        logger.warning(
            "Asset image-display-url: asset_not_found inventory_id=%s aisle_id=%s asset_id=%s",
            inventory_id,
            aisle_id,
            asset_id,
        )
        raise HTTPException(status_code=404, detail="Asset not found")

    def _asset_is_heic(a: SourceAsset) -> bool:
        mt = (a.mime_type or "").lower()
        if mt in ("image/heic", "image/heif"):
            return True
        if Path(a.storage_path or "").suffix.lower() in heic_extensions():
            return True
        if Path(a.original_filename or "").suffix.lower() in heic_extensions():
            return True
        return False

    if _asset_is_heic(asset):
        output_dir = Path(load_settings().output_dir)
        request_job_id = job_id.strip() if job_id and job_id.strip() else None
        normalized_path = resolve_normalized_asset_path(
            output_dir, job_repo, aisle_id, asset_id, job_id=job_id
        )
        if normalized_path is not None:
            return SourceAssetImageDisplayUrlResponse(
                image_url=None,
                requires_authenticated_fetch=True,
            )
        logger.warning(
            "Asset image-display-url: heic_preview_unavailable asset_id=%s request_job_id=%s",
            asset_id,
            request_job_id,
        )
        raise HTTPException(
            status_code=404,
            detail="Preview is not available for this image",
        )

    try:
        image_url, need_fetch = resolve_source_asset_image_display(asset, artifact_store=artifact_storage)
    except StoredArtifactAccessError as e:
        logger.warning(
            "Asset image-display-url resolution failed: %s asset_id=%s reason=%s",
            e.reason_code,
            asset_id,
            e.detail,
        )
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    return SourceAssetImageDisplayUrlResponse(
        image_url=image_url,
        requires_authenticated_fetch=need_fetch,
    )
