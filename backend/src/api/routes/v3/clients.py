"""v3 clients CRUD (Phase A1: create/get/list) and supplier reference images (Phase C2)."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from src.api.constants.error_wire import (
    HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED,
    HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED,
)
from src.api.constants.route_paths import API_V3_CLIENTS_ROUTER_PREFIX
from src.api.dependencies import (
    get_activate_supplier_extraction_profile_version_use_case,
    get_activate_supplier_prompt_config_version_use_case,
    get_artifact_storage,
    get_clone_supplier_extraction_profile_use_case,
    get_create_client_supplier_use_case,
    get_create_client_use_case,
    get_create_supplier_extraction_profile_version_use_case,
    get_create_supplier_prompt_config_version_use_case,
    get_delete_supplier_reference_image_use_case,
    get_get_active_supplier_extraction_profile_use_case,
    get_get_active_supplier_prompt_config_use_case,
    get_get_client_supplier_use_case,
    get_get_client_use_case,
    get_get_supplier_extraction_profile_by_version_use_case,
    get_get_supplier_prompt_config_use_case,
    get_get_supplier_reference_image_use_case,
    get_list_client_suppliers_use_case,
    get_list_clients_use_case,
    get_list_supplier_extraction_profiles_use_case,
    get_list_supplier_prompt_configs_use_case,
    get_list_supplier_reference_annotations_use_case,
    get_list_supplier_reference_images_use_case,
    get_replace_supplier_reference_annotations_use_case,
    get_update_client_use_case,
    get_upload_supplier_reference_images_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.asset_schemas import SourceAssetImageDisplayUrlResponse
from src.api.schemas.client_schemas import (
    ClientResponse,
    CreateClientRequest,
    PaginatedClientListResponse,
    UpdateClientRequest,
)
from src.api.schemas.client_supplier_schemas import (
    ClientSupplierResponse,
    CreateClientSupplierRequest,
    PaginatedClientSupplierListResponse,
)
from src.api.schemas.identification_mode_literals import (
    IdentificationModeLiteral,
    IdentificationModeSourceLiteral,
)
from src.api.schemas.listing_schemas import compute_total_pages
from src.api.schemas.supplier_extraction_profile_schemas import (
    CloneSupplierExtractionProfileRequest,
    CreateSupplierExtractionProfileRequest,
    ReferenceAnnotationResponse,
    ReplaceSupplierReferenceAnnotationsRequest,
    SupplierExtractionProfileResponse,
    SupplierExtractionProfilesListResponse,
    SupplierReferenceAnnotationsListResponse,
    TestExtractionProfileRequest,
    TestExtractionProfileResponse,
)
from src.api.schemas.supplier_prompt_config_schemas import (
    CreateSupplierPromptConfigRequest,
    SupplierPromptConfigResponse,
    SupplierPromptConfigsListResponse,
)
from src.api.schemas.supplier_reference_image_schemas import (
    DeleteSupplierReferenceImageResponse,
    SupplierReferenceImageResponse,
    SupplierReferenceImagesListResponse,
    UploadSupplierReferenceImagesResponse,
)
from src.api.services.identification_mode_response import client_identification_fields
from src.api.services.v3_stored_artifact_access import (
    StoredArtifactAccessError,
    resolve_supplier_reference_image_display,
    resolve_supplier_reference_image_file_response,
)
from src.application.errors import (
    DuplicateClientSupplierNameError,
    InvalidClientNameError,
    InvalidClientSupplierNameError,
    SupplierExtractionProfileNotFoundError,
    SupplierPromptConfigNotFoundError,
)
from src.application.services.optional_unset import UNSET
from src.application.use_cases.clients.create_client import CreateClientCommand, CreateClientUseCase
from src.application.use_cases.clients.get_client import GetClientUseCase
from src.application.use_cases.clients.list_clients import ListClientsUseCase
from src.application.use_cases.clients.update_client import (
    UpdateClientCommand,
    UpdateClientUseCase,
)
from src.application.use_cases.suppliers.create_client_supplier import (
    CreateClientSupplierCommand,
    CreateClientSupplierUseCase,
)
from src.application.use_cases.suppliers.get_client_supplier import GetClientSupplierUseCase
from src.application.use_cases.suppliers.list_client_suppliers import ListClientSuppliersUseCase
from src.application.use_cases.suppliers.manage_supplier_extraction_profiles import (
    ActivateSupplierExtractionProfileVersionCommand,
    ActivateSupplierExtractionProfileVersionUseCase,
    CloneSupplierExtractionProfileCommand,
    CloneSupplierExtractionProfileUseCase,
    CreateSupplierExtractionProfileVersionCommand,
    CreateSupplierExtractionProfileVersionUseCase,
    GetActiveSupplierExtractionProfileCommand,
    GetActiveSupplierExtractionProfileUseCase,
    GetSupplierExtractionProfileByVersionCommand,
    GetSupplierExtractionProfileByVersionUseCase,
    ListSupplierExtractionProfilesCommand,
    ListSupplierExtractionProfilesUseCase,
    ListSupplierReferenceAnnotationsCommand,
    ListSupplierReferenceAnnotationsUseCase,
    ReplaceSupplierReferenceAnnotationsCommand,
    ReplaceSupplierReferenceAnnotationsUseCase,
)
from src.application.use_cases.suppliers.manage_supplier_prompt_configs import (
    ActivateSupplierPromptConfigVersionCommand,
    ActivateSupplierPromptConfigVersionUseCase,
    CreateSupplierPromptConfigVersionCommand,
    CreateSupplierPromptConfigVersionUseCase,
    GetActiveSupplierPromptConfigCommand,
    GetActiveSupplierPromptConfigUseCase,
    GetSupplierPromptConfigCommand,
    GetSupplierPromptConfigUseCase,
    ListSupplierPromptConfigsCommand,
    ListSupplierPromptConfigsUseCase,
)
from src.application.use_cases.suppliers.manage_supplier_reference_images import (
    DeleteSupplierReferenceImageUseCase,
    GetSupplierReferenceImageUseCase,
)
from src.application.use_cases.suppliers.test_extraction_profile_diagnostic import (
    TestExtractionProfileCommand,
    TestExtractionProfileUseCase,
)
from src.application.use_cases.suppliers.upload_supplier_reference_images import (
    ListSupplierReferenceImagesUseCase,
    UploadedSupplierReferenceImageFile,
    UploadSupplierReferenceImagesUseCase,
)
from src.auth.dependencies import get_current_admin
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.extraction_profile import (
    ReferenceAnnotation,
    SupplierExtractionProfile,
)
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.domain.client_supplier.reference_image import SupplierReferenceImage

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=API_V3_CLIENTS_ROUTER_PREFIX,
    tags=["clients-v3"],
    dependencies=[Depends(get_current_admin)],
)


def _to_response(client: Client) -> ClientResponse:
    id_fields = client_identification_fields(client)
    return ClientResponse(
        id=client.id,
        name=client.name,
        status=client.status.value,
        created_at=client.created_at,
        updated_at=client.updated_at,
        identification_mode=cast(
            IdentificationModeLiteral | None, id_fields.identification_mode
        ),
        effective_identification_mode=cast(
            IdentificationModeLiteral, id_fields.effective_identification_mode
        ),
        identification_mode_source=cast(
            IdentificationModeSourceLiteral, id_fields.identification_mode_source
        ),
    )


def _to_supplier_response(supplier: ClientSupplier) -> ClientSupplierResponse:
    return ClientSupplierResponse(
        id=supplier.id,
        client_id=supplier.client_id,
        name=supplier.name,
        status=supplier.status.value,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )


def _supplier_reference_image_to_response(ref: SupplierReferenceImage) -> SupplierReferenceImageResponse:
    return SupplierReferenceImageResponse(
        id=ref.id,
        client_supplier_id=ref.client_supplier_id,
        filename=ref.filename,
        mime_type=ref.mime_type,
        file_size=ref.file_size,
        content_type=ref.content_type,
        file_size_bytes=ref.file_size_bytes,
        label=ref.label,
        description=ref.description,
        created_at=ref.created_at,
        updated_at=ref.updated_at,
    )


def _supplier_prompt_config_to_response(
    config: SupplierPromptConfig,
) -> SupplierPromptConfigResponse:
    return SupplierPromptConfigResponse(
        id=config.id,
        client_supplier_id=config.client_supplier_id,
        provider_name=config.provider_name,
        model_name=config.model_name,
        instructions_text=config.instructions_text,
        version=config.version,
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _supplier_extraction_profile_to_response(
    profile: SupplierExtractionProfile,
) -> SupplierExtractionProfileResponse:
    return SupplierExtractionProfileResponse(
        id=profile.id,
        client_id=profile.client_id,
        supplier_id=profile.supplier_id,
        profile_key=profile.profile_key,
        version=profile.version,
        status=profile.status.value,
        configuration=profile.configuration.to_public_dict(),
        visual_notes=profile.visual_notes,
        created_by=profile.created_by,
        created_at=profile.created_at,
        activated_by=profile.activated_by,
        activated_at=profile.activated_at,
        superseded_at=profile.superseded_at,
        updated_at=profile.updated_at,
        row_version=profile.row_version,
    )


def _reference_annotation_to_response(
    annotation: ReferenceAnnotation,
) -> ReferenceAnnotationResponse:
    polygon = (
        [[x, y] for x, y in annotation.normalized_polygon]
        if annotation.normalized_polygon
        else None
    )
    return ReferenceAnnotationResponse(
        id=annotation.id,
        template_image_id=annotation.template_image_id,
        profile_id=annotation.profile_id,
        field_key=annotation.field_key,
        anchor_texts=list(annotation.anchor_texts),
        spatial_relation=annotation.spatial_relation.value,
        normalized_polygon=polygon,
        priority=annotation.priority,
        required=annotation.required,
        max_distance_ratio=annotation.max_distance_ratio,
    )


async def _to_uploaded_supplier_reference_image_files(
    files: list[UploadFile],
    *,
    label: str | None,
    description: str | None,
) -> list[UploadedSupplierReferenceImageFile]:
    """Convert multipart parts to use-case DTOs (mirrors inventory visual-reference upload rules)."""
    if not files:
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED)
    lbl = (label or "").strip() or None
    desc = (description or "").strip() or None
    result: list[UploadedSupplierReferenceImageFile] = []
    for i, u in enumerate(files):
        has_name = bool(u.filename and u.filename.strip())
        has_type = bool(getattr(u, "content_type", None) and str(u.content_type).strip())
        if not has_name and not has_type:
            raise HTTPException(
                status_code=422,
                detail=f"File at index {i} has no filename and no content type; each part must be a valid file.",
            )
        content = await u.read()
        size = len(content)
        if size <= 0:
            raise HTTPException(
                status_code=422, detail=HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED
            )
        result.append(
            UploadedSupplierReferenceImageFile(
                original_filename=(u.filename or "file").strip(),
                file_obj=BytesIO(content),
                content_type=u.content_type or "application/octet-stream",
                size=size,
                label=lbl,
                description=desc,
            )
        )
    if not result:
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED)
    return result


@router.post("/", response_model=ClientResponse, status_code=201)
def create_client(
    payload: CreateClientRequest,
    use_case: CreateClientUseCase = Depends(get_create_client_use_case),
) -> ClientResponse:
    try:
        client = use_case.execute(
            CreateClientCommand(name=payload.name, status=ClientStatus(payload.status))
        )
    except InvalidClientNameError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _to_response(client)


@router.get("/", response_model=PaginatedClientListResponse)
def list_clients(
    use_case: ListClientsUseCase = Depends(get_list_clients_use_case),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> PaginatedClientListResponse:
    rows = list(use_case.execute())
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    window = rows[start:end]
    return PaginatedClientListResponse(
        items=[_to_response(item) for item in window],
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=compute_total_pages(total, page_size),
    )


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: str,
    use_case: GetClientUseCase = Depends(get_get_client_use_case),
) -> ClientResponse:
    try:
        client = use_case.execute(client_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _to_response(client)


@router.patch("/{client_id}", response_model=ClientResponse)
def update_client(
    client_id: str,
    payload: UpdateClientRequest,
    use_case: UpdateClientUseCase = Depends(get_update_client_use_case),
) -> ClientResponse:
    try:
        client = use_case.execute(
            UpdateClientCommand(
                client_id=client_id,
                name=payload.name,
                identification_mode=(
                    payload.identification_mode
                    if "identification_mode" in payload.model_fields_set
                    else UNSET
                ),
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _to_response(client)


@router.post("/{client_id}/suppliers", response_model=ClientSupplierResponse, status_code=201)
def create_client_supplier(
    client_id: str,
    payload: CreateClientSupplierRequest,
    use_case: CreateClientSupplierUseCase = Depends(get_create_client_supplier_use_case),
) -> ClientSupplierResponse:
    try:
        supplier = use_case.execute(
            CreateClientSupplierCommand(
                client_id=client_id,
                name=payload.name,
                status=ClientSupplierStatus(payload.status),
            )
        )
    except InvalidClientSupplierNameError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except DuplicateClientSupplierNameError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _to_supplier_response(supplier)


@router.get("/{client_id}/suppliers", response_model=PaginatedClientSupplierListResponse)
def list_client_suppliers(
    client_id: str,
    use_case: ListClientSuppliersUseCase = Depends(get_list_client_suppliers_use_case),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> PaginatedClientSupplierListResponse:
    try:
        rows = list(use_case.execute(client_id))
    except Exception as e:
        reraise_if_mapped(e)
        raise
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    window = rows[start:end]
    return PaginatedClientSupplierListResponse(
        items=[_to_supplier_response(item) for item in window],
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=compute_total_pages(total, page_size),
    )


@router.get("/{client_id}/suppliers/{supplier_id}", response_model=ClientSupplierResponse)
def get_client_supplier(
    client_id: str,
    supplier_id: str,
    use_case: GetClientSupplierUseCase = Depends(get_get_client_supplier_use_case),
) -> ClientSupplierResponse:
    try:
        supplier = use_case.execute(client_id, supplier_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _to_supplier_response(supplier)


@router.get(
    "/{client_id}/suppliers/{supplier_id}/reference-images",
    response_model=SupplierReferenceImagesListResponse,
)
def list_supplier_reference_images(
    client_id: str,
    supplier_id: str,
    use_case: ListSupplierReferenceImagesUseCase = Depends(
        get_list_supplier_reference_images_use_case
    ),
) -> SupplierReferenceImagesListResponse:
    try:
        refs = use_case.execute(client_id, supplier_id)
        return SupplierReferenceImagesListResponse(
            items=[_supplier_reference_image_to_response(ref) for ref in refs]
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{client_id}/suppliers/{supplier_id}/reference-images",
    response_model=UploadSupplierReferenceImagesResponse,
    status_code=201,
)
async def upload_supplier_reference_images(
    client_id: str,
    supplier_id: str,
    files: list[UploadFile] = File(
        ...,
        description=(
            "One or more image parts named `files`. Optional form fields `label` and `description` "
            "apply to every `files` part in this request (same metadata on each created row when "
            "multiple files are uploaded)."
        ),
    ),
    label: str | None = Form(
        None,
        description=(
            "Optional label applied to every uploaded file in this request (same value for each `files` part)."
        ),
    ),
    description: str | None = Form(
        None,
        description=(
            "Optional description applied to every uploaded file in this request (same value for each `files` part)."
        ),
    ),
    use_case: UploadSupplierReferenceImagesUseCase = Depends(
        get_upload_supplier_reference_images_use_case
    ),
) -> UploadSupplierReferenceImagesResponse:
    uploaded = await _to_uploaded_supplier_reference_image_files(
        files, label=label, description=description
    )
    try:
        created = use_case.execute(client_id, supplier_id, uploaded)
        return UploadSupplierReferenceImagesResponse(
            items=[_supplier_reference_image_to_response(ref) for ref in created]
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.delete(
    "/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}",
    response_model=DeleteSupplierReferenceImageResponse,
)
def delete_supplier_reference_image(
    client_id: str,
    supplier_id: str,
    image_id: str,
    use_case: DeleteSupplierReferenceImageUseCase = Depends(
        get_delete_supplier_reference_image_use_case
    ),
) -> DeleteSupplierReferenceImageResponse:
    try:
        use_case.execute(client_id, supplier_id, image_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return DeleteSupplierReferenceImageResponse(deleted=True, id=image_id)


def _supplier_reference_image_display_response(
    *,
    image_url: str | None,
    need_fetch: bool,
) -> SourceAssetImageDisplayUrlResponse:
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


@router.get(
    "/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/image-display-url",
    response_model=SourceAssetImageDisplayUrlResponse,
)
def get_supplier_reference_image_display_url(
    client_id: str,
    supplier_id: str,
    image_id: str,
    use_case: GetSupplierReferenceImageUseCase = Depends(
        get_get_supplier_reference_image_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> SourceAssetImageDisplayUrlResponse:
    """Return how to display a supplier reference image: presigned URL or authenticated GET on ``.../file``."""
    try:
        image = use_case.execute(client_id, supplier_id, image_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    try:
        image_url, need_fetch = resolve_supplier_reference_image_display(
            image, artifact_store=artifact_storage
        )
    except StoredArtifactAccessError as e:
        logger.warning(
            "Supplier reference image-display-url failed: client_id=%s supplier_id=%s image_id=%s reason=%s",
            client_id,
            supplier_id,
            image_id,
            e.reason_code,
        )
        reraise_if_mapped(e, cause=e)
        raise
    return _supplier_reference_image_display_response(image_url=image_url, need_fetch=need_fetch)


@router.get("/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/file")
def get_supplier_reference_image_file(
    client_id: str,
    supplier_id: str,
    image_id: str,
    use_case: GetSupplierReferenceImageUseCase = Depends(
        get_get_supplier_reference_image_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> Response:
    try:
        image = use_case.execute(client_id, supplier_id, image_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise

    try:
        return resolve_supplier_reference_image_file_response(
            image, artifact_store=artifact_storage
        )
    except StoredArtifactAccessError as e:
        logger.warning(
            "Supplier reference image file resolution failed: client_id=%s supplier_id=%s image_id=%s reason=%s detail=%s",
            client_id,
            supplier_id,
            image_id,
            e.reason_code,
            e.detail,
        )
        reraise_if_mapped(e, cause=e)
        raise


@router.get(
    "/{client_id}/suppliers/{supplier_id}/prompt-configs",
    response_model=SupplierPromptConfigsListResponse,
)
def list_supplier_prompt_configs(
    client_id: str,
    supplier_id: str,
    scope: str | None = Query(None),
    provider_name: str | None = Query(None),
    model_name: str | None = Query(None),
    use_case: ListSupplierPromptConfigsUseCase = Depends(get_list_supplier_prompt_configs_use_case),
) -> SupplierPromptConfigsListResponse:
    try:
        rows = use_case.execute(
            ListSupplierPromptConfigsCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                scope=scope,
                provider_name=provider_name,
                model_name=model_name,
            )
        )
        return SupplierPromptConfigsListResponse(
            items=[_supplier_prompt_config_to_response(row) for row in rows]
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{client_id}/suppliers/{supplier_id}/prompt-configs",
    response_model=SupplierPromptConfigResponse,
    status_code=201,
)
def create_supplier_prompt_config(
    client_id: str,
    supplier_id: str,
    payload: CreateSupplierPromptConfigRequest,
    use_case: CreateSupplierPromptConfigVersionUseCase = Depends(
        get_create_supplier_prompt_config_version_use_case
    ),
) -> SupplierPromptConfigResponse:
    try:
        created = use_case.execute(
            CreateSupplierPromptConfigVersionCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                provider_name=payload.provider_name,
                model_name=payload.model_name,
                instructions_text=payload.instructions_text,
                activate=payload.activate,
            )
        )
        return _supplier_prompt_config_to_response(created)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{client_id}/suppliers/{supplier_id}/prompt-configs/active",
    response_model=SupplierPromptConfigResponse,
)
def get_active_supplier_prompt_config(
    client_id: str,
    supplier_id: str,
    provider_name: str | None = Query(None),
    model_name: str | None = Query(None),
    use_case: GetActiveSupplierPromptConfigUseCase = Depends(
        get_get_active_supplier_prompt_config_use_case
    ),
) -> SupplierPromptConfigResponse:
    try:
        active = use_case.execute(
            GetActiveSupplierPromptConfigCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                provider_name=provider_name,
                model_name=model_name,
            )
        )
        if active is None:
            raise SupplierPromptConfigNotFoundError(
                "Supplier prompt config not found in requested scope"
            )
        return _supplier_prompt_config_to_response(active)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{client_id}/suppliers/{supplier_id}/prompt-configs/{config_id}",
    response_model=SupplierPromptConfigResponse,
)
def get_supplier_prompt_config(
    client_id: str,
    supplier_id: str,
    config_id: str,
    use_case: GetSupplierPromptConfigUseCase = Depends(get_get_supplier_prompt_config_use_case),
) -> SupplierPromptConfigResponse:
    try:
        row = use_case.execute(
            GetSupplierPromptConfigCommand(
                client_id=client_id, supplier_id=supplier_id, config_id=config_id
            )
        )
        return _supplier_prompt_config_to_response(row)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{client_id}/suppliers/{supplier_id}/prompt-configs/{config_id}/activate",
    response_model=SupplierPromptConfigResponse,
)
def activate_supplier_prompt_config(
    client_id: str,
    supplier_id: str,
    config_id: str,
    use_case: ActivateSupplierPromptConfigVersionUseCase = Depends(
        get_activate_supplier_prompt_config_version_use_case
    ),
) -> SupplierPromptConfigResponse:
    try:
        activated = use_case.execute(
            ActivateSupplierPromptConfigVersionCommand(
                client_id=client_id, supplier_id=supplier_id, config_id=config_id
            )
        )
        return _supplier_prompt_config_to_response(activated)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{client_id}/suppliers/{supplier_id}/extraction-profiles",
    response_model=SupplierExtractionProfilesListResponse,
)
def list_supplier_extraction_profiles(
    client_id: str,
    supplier_id: str,
    use_case: ListSupplierExtractionProfilesUseCase = Depends(
        get_list_supplier_extraction_profiles_use_case
    ),
) -> SupplierExtractionProfilesListResponse:
    try:
        rows = use_case.execute(
            ListSupplierExtractionProfilesCommand(
                client_id=client_id, supplier_id=supplier_id
            )
        )
        return SupplierExtractionProfilesListResponse(
            items=[_supplier_extraction_profile_to_response(row) for row in rows]
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{client_id}/suppliers/{supplier_id}/extraction-profiles",
    response_model=SupplierExtractionProfileResponse,
    status_code=201,
)
def create_supplier_extraction_profile(
    client_id: str,
    supplier_id: str,
    payload: CreateSupplierExtractionProfileRequest,
    use_case: CreateSupplierExtractionProfileVersionUseCase = Depends(
        get_create_supplier_extraction_profile_version_use_case
    ),
) -> SupplierExtractionProfileResponse:
    try:
        created = use_case.execute(
            CreateSupplierExtractionProfileVersionCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                configuration=payload.configuration,
                visual_notes=payload.visual_notes,
                profile_key=payload.profile_key,
                activate=payload.activate,
            )
        )
        return _supplier_extraction_profile_to_response(created)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{client_id}/suppliers/{supplier_id}/extraction-profiles/active",
    response_model=SupplierExtractionProfileResponse,
)
def get_active_supplier_extraction_profile(
    client_id: str,
    supplier_id: str,
    use_case: GetActiveSupplierExtractionProfileUseCase = Depends(
        get_get_active_supplier_extraction_profile_use_case
    ),
) -> SupplierExtractionProfileResponse:
    try:
        active = use_case.execute(
            GetActiveSupplierExtractionProfileCommand(
                client_id=client_id, supplier_id=supplier_id
            )
        )
        if active is None:
            raise SupplierExtractionProfileNotFoundError(
                "Supplier extraction profile not found in requested scope"
            )
        return _supplier_extraction_profile_to_response(active)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{client_id}/suppliers/{supplier_id}/extraction-profiles/versions/{version}",
    response_model=SupplierExtractionProfileResponse,
)
def get_supplier_extraction_profile_by_version(
    client_id: str,
    supplier_id: str,
    version: int,
    use_case: GetSupplierExtractionProfileByVersionUseCase = Depends(
        get_get_supplier_extraction_profile_by_version_use_case
    ),
) -> SupplierExtractionProfileResponse:
    try:
        row = use_case.execute(
            GetSupplierExtractionProfileByVersionCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                version=version,
            )
        )
        return _supplier_extraction_profile_to_response(row)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{client_id}/suppliers/{supplier_id}/extraction-profiles/clone",
    response_model=SupplierExtractionProfileResponse,
    status_code=201,
)
def clone_supplier_extraction_profile(
    client_id: str,
    supplier_id: str,
    payload: CloneSupplierExtractionProfileRequest,
    use_case: CloneSupplierExtractionProfileUseCase = Depends(
        get_clone_supplier_extraction_profile_use_case
    ),
) -> SupplierExtractionProfileResponse:
    try:
        cloned = use_case.execute(
            CloneSupplierExtractionProfileCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                source_profile_id=payload.source_profile_id,
            )
        )
        return _supplier_extraction_profile_to_response(cloned)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{client_id}/suppliers/{supplier_id}/extraction-profiles/test",
    response_model=TestExtractionProfileResponse,
)
def test_supplier_extraction_profile(
    client_id: str,
    supplier_id: str,
    payload: TestExtractionProfileRequest,
    get_supplier: GetClientSupplierUseCase = Depends(get_get_client_supplier_use_case),
) -> TestExtractionProfileResponse:
    """Diagnostic OCR/profile dry-run — never creates positions."""
    import base64
    import binascii

    # Scope: supplier must belong to client (admin router already gates role).
    get_supplier.execute(client_id=client_id, supplier_id=supplier_id)

    try:
        raw = payload.image_base64
        if "," in raw and raw.strip().lower().startswith("data:"):
            raw = raw.split(",", 1)[1]
        image_bytes = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="INVALID_IMAGE_BASE64") from exc

    try:
        result = TestExtractionProfileUseCase().execute(
            TestExtractionProfileCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                configuration=payload.configuration,
                image_bytes=image_bytes,
            )
        )
        return TestExtractionProfileResponse(**result)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{client_id}/suppliers/{supplier_id}/extraction-profiles/{profile_id}/activate",
    response_model=SupplierExtractionProfileResponse,
)
def activate_supplier_extraction_profile(
    client_id: str,
    supplier_id: str,
    profile_id: str,
    expected_row_version: int | None = Query(None),
    use_case: ActivateSupplierExtractionProfileVersionUseCase = Depends(
        get_activate_supplier_extraction_profile_version_use_case
    ),
) -> SupplierExtractionProfileResponse:
    try:
        activated = use_case.execute(
            ActivateSupplierExtractionProfileVersionCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                profile_id=profile_id,
                expected_row_version=expected_row_version,
            )
        )
        return _supplier_extraction_profile_to_response(activated)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations",
    response_model=SupplierReferenceAnnotationsListResponse,
)
def list_supplier_reference_annotations(
    client_id: str,
    supplier_id: str,
    image_id: str,
    use_case: ListSupplierReferenceAnnotationsUseCase = Depends(
        get_list_supplier_reference_annotations_use_case
    ),
) -> SupplierReferenceAnnotationsListResponse:
    try:
        rows = use_case.execute(
            ListSupplierReferenceAnnotationsCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                image_id=image_id,
            )
        )
        return SupplierReferenceAnnotationsListResponse(
            items=[_reference_annotation_to_response(row) for row in rows]
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.put(
    "/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations",
    response_model=SupplierReferenceAnnotationsListResponse,
)
def replace_supplier_reference_annotations(
    client_id: str,
    supplier_id: str,
    image_id: str,
    payload: ReplaceSupplierReferenceAnnotationsRequest,
    use_case: ReplaceSupplierReferenceAnnotationsUseCase = Depends(
        get_replace_supplier_reference_annotations_use_case
    ),
) -> SupplierReferenceAnnotationsListResponse:
    try:
        rows = use_case.execute(
            ReplaceSupplierReferenceAnnotationsCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                image_id=image_id,
                profile_id=payload.profile_id,
                annotations=[item.model_dump() for item in payload.annotations],
            )
        )
        return SupplierReferenceAnnotationsListResponse(
            items=[_reference_annotation_to_response(row) for row in rows]
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise

