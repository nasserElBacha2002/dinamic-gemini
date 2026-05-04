"""v3 aisle assets: upload, list, file serving."""

from __future__ import annotations

import logging
from enum import Enum
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

from src.api.constants.error_wire import (
    HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY,
    HTTP_DETAIL_AISLE_NOT_FOUND_SHORT,
    HTTP_DETAIL_ASSET_NOT_FOUND,
    HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED,
    HTTP_DETAIL_PREVIEW_NOT_AVAILABLE_FOR_IMAGE,
)
from src.api.dependencies import (
    get_artifact_storage,
    get_delete_aisle_source_asset_use_case,
    get_list_aisle_assets_use_case,
    get_result_context_resolver,
    get_upload_aisle_assets_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.asset_schemas import (
    SourceAssetImageDisplayUrlResponse,
    SourceAssetResponse,
    UploadAisleAssetsResponse,
)
from src.api.services.v3_stored_artifact_access import (
    StoredArtifactAccessError,
    resolve_source_asset_file_response,
    resolve_source_asset_image_display,
)
from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import AisleNotFoundError
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.delete_aisle_source_asset import DeleteAisleSourceAssetUseCase
from src.application.use_cases.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.upload_aisle_assets import UploadAisleAssetsUseCase
from src.config import load_settings
from src.domain.assets.entities import SourceAsset

from .shared import asset_to_response, heic_extensions, resolve_normalized_asset_path

logger = logging.getLogger(__name__)
router = APIRouter()


def _source_asset_image_display_response(
    *,
    image_url: str | None,
    need_fetch: bool,
) -> SourceAssetImageDisplayUrlResponse:
    """Build API model; ``need_fetch`` must be true when ``image_url`` is None."""
    if image_url:
        return SourceAssetImageDisplayUrlResponse(
            image_url=image_url,
            requires_authenticated_fetch=False,
            display_strategy="presigned_url",
        )
    return SourceAssetImageDisplayUrlResponse(
        image_url=None,
        requires_authenticated_fetch=True,
        display_strategy="authenticated_file_fetch",
    )


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
    files: list[UploadFile] = File(..., description="One or more image or video files"),
    use_case: UploadAisleAssetsUseCase = Depends(get_upload_aisle_assets_use_case),
) -> UploadAisleAssetsResponse:
    """Upload one or more assets (photos/videos) to an aisle. Aisle transitions to assets_uploaded."""
    if not files:
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED)
    uploaded: list[UploadedFile] = []
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
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED)
    try:
        created = use_case.execute(inventory_id, aisle_id, uploaded)
        return UploadAisleAssetsResponse(assets=[asset_to_response(a) for a in created])
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get("/{inventory_id}/aisles/{aisle_id}/assets", response_model=list[SourceAssetResponse])
def list_aisle_assets(
    inventory_id: str,
    aisle_id: str,
    use_case: ListAisleAssetsUseCase = Depends(get_list_aisle_assets_use_case),
) -> list[SourceAssetResponse]:
    """List source assets for an aisle."""
    try:
        assets = use_case.execute(inventory_id, aisle_id)
        return [asset_to_response(a) for a in assets]
    except AisleNotFoundError as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file",
    response_model=None,
    response_class=FileResponse,
)
def get_aisle_asset_file(
    inventory_id: str,
    aisle_id: str,
    asset_id: str,
    job_id: str | None = Query(
        None,
        description=(
            "Optional inventory job id for HEIC normalized preview; must match a run for this aisle. "
            "Omitted uses ResultContextResolver (operational job or legacy — legacy has no normalized folder)."
        ),
    ),
    use_case: ListAisleAssetsUseCase = Depends(get_list_aisle_assets_use_case),
    resolver: ResultContextResolver = Depends(get_result_context_resolver),
    artifact_storage=Depends(get_artifact_storage),
) -> Response:
    """Serve the reference image/file for an aisle asset. HEIC/HEIF: serves normalized JPG when available (optional job_id)."""
    failure_reason: AssetFileFailureReason | None = None
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
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY)
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
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_ASSET_NOT_FOUND)

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
        try:
            aisle_row = use_case.get_validated_aisle(inventory_id, aisle_id)
        except AisleNotFoundError:
            failure_reason = AssetFileFailureReason.AISLE_NOT_FOUND
            raise HTTPException(status_code=404, detail=HTTP_DETAIL_AISLE_NOT_FOUND_SHORT) from None
        output_dir = Path(load_settings().output_dir)
        request_job_id = job_id.strip() if job_id and job_id.strip() else None
        logger.debug(
            "Asset file: HEIC resolving normalized path asset_id=%s job_id=%s",
            asset_id,
            request_job_id,
        )
        normalized_path = resolve_normalized_asset_path(
            output_dir,
            inventory_id=inventory_id,
            aisle=aisle_row,
            asset_id=asset_id,
            explicit_job_id=request_job_id,
            resolver=resolver,
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
            detail=HTTP_DETAIL_PREVIEW_NOT_AVAILABLE_FOR_IMAGE,
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
        reraise_if_mapped(e, cause=e)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url",
    response_model=SourceAssetImageDisplayUrlResponse,
)
def get_aisle_asset_image_display_url(
    inventory_id: str,
    aisle_id: str,
    asset_id: str,
    job_id: str | None = Query(
        None,
        description="Optional job id to align HEIC preview with the /file endpoint (resolver semantics).",
    ),
    use_case: ListAisleAssetsUseCase = Depends(get_list_aisle_assets_use_case),
    resolver: ResultContextResolver = Depends(get_result_context_resolver),
    artifact_storage=Depends(get_artifact_storage),
) -> SourceAssetImageDisplayUrlResponse:
    """Return how to display the asset image: presigned URL or authenticated GET on ``.../file``."""
    try:
        assets = use_case.execute(inventory_id, aisle_id)
    except AisleNotFoundError:
        logger.warning(
            "Asset image-display-url: aisle_not_found inventory_id=%s aisle_id=%s asset_id=%s",
            inventory_id,
            aisle_id,
            asset_id,
        )
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY)
    asset = next((a for a in assets if a.id == asset_id), None)
    if asset is None:
        logger.warning(
            "Asset image-display-url: asset_not_found inventory_id=%s aisle_id=%s asset_id=%s",
            inventory_id,
            aisle_id,
            asset_id,
        )
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_ASSET_NOT_FOUND)

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
        try:
            aisle_row = use_case.get_validated_aisle(inventory_id, aisle_id)
        except AisleNotFoundError:
            logger.warning(
                "Asset image-display-url: aisle_not_found inventory_id=%s aisle_id=%s asset_id=%s",
                inventory_id,
                aisle_id,
                asset_id,
            )
            raise HTTPException(status_code=404, detail=HTTP_DETAIL_AISLE_NOT_FOUND_SHORT) from None
        output_dir = Path(load_settings().output_dir)
        request_job_id = job_id.strip() if job_id and job_id.strip() else None
        normalized_path = resolve_normalized_asset_path(
            output_dir,
            inventory_id=inventory_id,
            aisle=aisle_row,
            asset_id=asset_id,
            explicit_job_id=request_job_id,
            resolver=resolver,
        )
        if normalized_path is not None:
            # Same strategy as local/legacy: client must GET /file, which serves the normalized JPEG.
            return SourceAssetImageDisplayUrlResponse(
                image_url=None,
                requires_authenticated_fetch=True,
                display_strategy="authenticated_file_fetch",
            )
        logger.warning(
            "Asset image-display-url: heic_preview_unavailable asset_id=%s request_job_id=%s",
            asset_id,
            request_job_id,
        )
        raise HTTPException(
            status_code=404,
            detail=HTTP_DETAIL_PREVIEW_NOT_AVAILABLE_FOR_IMAGE,
        )

    try:
        image_url, need_fetch = resolve_source_asset_image_display(
            asset, artifact_store=artifact_storage
        )
    except StoredArtifactAccessError as e:
        logger.warning(
            "Asset image-display-url resolution failed: %s asset_id=%s reason=%s",
            e.reason_code,
            asset_id,
            e.detail,
        )
        reraise_if_mapped(e, cause=e)

    return _source_asset_image_display_response(image_url=image_url, need_fetch=need_fetch)


@router.delete(
    "/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}",
    status_code=204,
    response_model=None,
)
def delete_aisle_source_asset(
    inventory_id: str,
    aisle_id: str,
    asset_id: str,
    use_case: DeleteAisleSourceAssetUseCase = Depends(get_delete_aisle_source_asset_use_case),
) -> None:
    """Remove one uploaded source asset for the aisle (DB row + stored object best-effort)."""
    try:
        use_case.execute(inventory_id, aisle_id, asset_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
