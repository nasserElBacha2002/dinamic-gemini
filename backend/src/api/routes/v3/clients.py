"""v3 clients CRUD (Phase A1: create/get/list) and supplier reference images (Phase C2)."""

from __future__ import annotations

import logging
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from src.api.constants.error_wire import (
    HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED,
    HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED,
)
from src.api.constants.route_paths import API_V3_CLIENTS_ROUTER_PREFIX
from src.api.dependencies import (
    get_activate_supplier_prompt_config_version_use_case,
    get_artifact_storage,
    get_create_client_supplier_use_case,
    get_create_client_use_case,
    get_create_supplier_prompt_config_version_use_case,
    get_delete_supplier_reference_image_use_case,
    get_get_active_supplier_prompt_config_use_case,
    get_get_client_supplier_use_case,
    get_get_client_use_case,
    get_get_supplier_prompt_config_use_case,
    get_get_supplier_reference_image_use_case,
    get_list_client_suppliers_use_case,
    get_list_clients_use_case,
    get_list_supplier_prompt_configs_use_case,
    get_list_supplier_reference_images_use_case,
    get_upload_supplier_reference_images_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.client_schemas import (
    ClientResponse,
    CreateClientRequest,
    PaginatedClientListResponse,
)
from src.api.schemas.client_supplier_schemas import (
    ClientSupplierResponse,
    CreateClientSupplierRequest,
    PaginatedClientSupplierListResponse,
)
from src.api.schemas.listing_schemas import compute_total_pages
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
from src.api.services.v3_stored_artifact_access import (
    StoredArtifactAccessError,
    resolve_supplier_reference_image_file_response,
)
from src.application.errors import (
    DuplicateClientSupplierNameError,
    InvalidClientNameError,
    InvalidClientSupplierNameError,
    SupplierPromptConfigNotFoundError,
)
from src.application.use_cases.clients.create_client import CreateClientCommand, CreateClientUseCase
from src.application.use_cases.clients.get_client import GetClientUseCase
from src.application.use_cases.clients.list_clients import ListClientsUseCase
from src.application.use_cases.suppliers.create_client_supplier import (
    CreateClientSupplierCommand,
    CreateClientSupplierUseCase,
)
from src.application.use_cases.suppliers.get_client_supplier import GetClientSupplierUseCase
from src.application.use_cases.suppliers.list_client_suppliers import ListClientSuppliersUseCase
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
from src.application.use_cases.suppliers.upload_supplier_reference_images import (
    ListSupplierReferenceImagesUseCase,
    UploadedSupplierReferenceImageFile,
    UploadSupplierReferenceImagesUseCase,
)
from src.auth.dependencies import get_current_admin
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.domain.client_supplier.reference_image import SupplierReferenceImage

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=API_V3_CLIENTS_ROUTER_PREFIX,
    tags=["clients-v3"],
    dependencies=[Depends(get_current_admin)],
)


def _to_response(client: Client) -> ClientResponse:
    return ClientResponse(
        id=client.id,
        name=client.name,
        status=client.status.value,
        created_at=client.created_at,
        updated_at=client.updated_at,
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

