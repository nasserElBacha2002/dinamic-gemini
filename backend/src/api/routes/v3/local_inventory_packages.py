"""v3 local inventory ZIP package import endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.datastructures import UploadFile

from src.api.dependencies import (
    get_confirm_local_inventory_package_use_case,
    get_get_local_inventory_package_use_case,
    get_preview_local_inventory_package_use_case,
    require_inventory_client_scope,
)
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.local_csv_import_schemas import (
    LocalCsvImportResponse,
    LocalCsvImportRowResponse,
)
from src.api.schemas.local_inventory_package_schemas import (
    ConfirmLocalInventoryPackageRequest,
    LocalInventoryPackagePhotoResponse,
    LocalInventoryPackageResponse,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.use_cases.inventories.manage_local_inventory_package import (
    ConfirmLocalInventoryPackage,
    GetLocalInventoryPackage,
    PreviewLocalInventoryPackage,
)
from src.config import load_settings
from src.domain.local_csv_import.entities import LocalCsvImport
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.domain.local_inventory_package.entities import LocalInventoryPackage
from src.domain.local_inventory_package.errors import (
    PACKAGE_EXPORT_CONFLICT,
    PACKAGE_IMPORT_DISABLED,
    PACKAGE_NOT_FOUND,
    LocalInventoryPackageDisabledError,
    LocalInventoryPackageImportError,
)

router = APIRouter()


def _csv_response(record: LocalCsvImport, *, duplicate: bool = False) -> LocalCsvImportResponse:
    return LocalCsvImportResponse(
        import_id=record.id,
        export_id=record.export_id,
        schema_version=record.schema_version,
        inventory_id=record.inventory_id,
        status=record.status,
        total_rows=record.total_rows,
        valid_rows=record.valid_rows,
        rejected_rows=record.rejected_rows,
        duplicate_rows=record.duplicate_rows,
        duplicate=duplicate,
        created_at=record.created_at,
        confirmed_at=record.confirmed_at,
        confirmed_by_user_id=record.confirmed_by_user_id,
        rows=[
            LocalCsvImportRowResponse(
                row_number=row.row_number,
                aisle_id=row.aisle_id,
                capture_session_id=row.capture_session_id,
                capture_photo_id=row.capture_photo_id,
                client_file_id=row.client_file_id,
                capture_order=row.capture_order,
                captured_at=row.captured_at,
                position_code=row.position_code,
                internal_code=row.internal_code,
                quantity=row.quantity,
                quantity_status=row.quantity_status,
                detection_status=row.detection_status,
                source=row.detection_source,
                ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,  # type: ignore[arg-type]
                requires_review=row.requires_review,
                error_code=row.error_code,
                notes=row.notes,
                status=row.status,
                productive_result_id=row.productive_result_id,
                validation_errors=list(row.validation_errors),
                validation_warnings=list(row.validation_warnings),
            )
            for row in record.rows
        ],
    )


def _response(
    record: LocalInventoryPackage, *, duplicate: bool = False
) -> LocalInventoryPackageResponse:
    return LocalInventoryPackageResponse(
        package_id=record.id,
        export_id=record.export_id,
        inventory_id=record.inventory_id,
        csv_import_id=record.csv_import_id,
        package_kind=record.package_kind,
        package_version=record.package_version,
        status=record.status,
        expected_photo_count=record.expected_photo_count,
        included_photo_count=record.included_photo_count,
        package_checksum_sha256=record.package_checksum_sha256,
        csv_checksum_sha256=record.csv_checksum_sha256,
        aisle_id=record.aisle_id,
        capture_session_id=record.capture_session_id,
        freeze_id=record.freeze_id,
        duplicate=duplicate,
        created_at=record.created_at,
        confirmed_at=record.confirmed_at,
        confirmed_by_user_id=record.confirmed_by_user_id,
        photos=[
            LocalInventoryPackagePhotoResponse(
                capture_photo_id=p.capture_photo_id,
                client_file_id=p.client_file_id,
                sequence_number=p.sequence_number,
                file_name=p.file_name,
                mime_type=p.mime_type,
                size_bytes=p.size_bytes,
                sha256=p.sha256,
                width=p.width,
                height=p.height,
                asset_variant=p.asset_variant,
                source_asset_id=p.source_asset_id,
            )
            for p in record.photos
        ],
        csv_import=_csv_response(record.csv_import) if record.csv_import else None,
    )


def _raise_package_error(exc: LocalInventoryPackageImportError) -> None:
    status = 422
    if exc.code in {
        PACKAGE_IMPORT_DISABLED,
        PACKAGE_NOT_FOUND,
        "INVENTORY_NOT_FOUND",
        "PACKAGE_AISLE_NOT_FOUND",
    }:
        status = 404
    elif exc.code in {PACKAGE_EXPORT_CONFLICT, "LOCAL_CSV_SECONDARY_CONFLICT"}:
        status = 409
    elif exc.code in {"PACKAGE_UNCOMPRESSED_TOO_LARGE", "PACKAGE_FILE_TOO_LARGE"}:
        status = 413
    raise StructuredApiHttpError(status, error_code=exc.code, detail=str(exc)) from exc


async def _read_zip_request(request: Request, max_bytes: int) -> bytes:
    content_type = (request.headers.get("content-type") or "").lower()
    length = request.headers.get("content-length")
    if "multipart/form-data" not in content_type and length:
        try:
            if int(length) > max_bytes:
                raise StructuredApiHttpError(
                    413,
                    error_code="LOCAL_INVENTORY_PACKAGE_TOO_LARGE",
                    detail=f"Package exceeds configured {max_bytes} byte limit",
                )
        except ValueError:
            pass

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise StructuredApiHttpError(
                422,
                error_code="LOCAL_INVENTORY_PACKAGE_FILE_REQUIRED",
                detail="multipart field `file` is required",
            )
        content = await upload.read()
    else:
        content = await request.body()

    if len(content) > max_bytes:
        raise StructuredApiHttpError(
            413,
            error_code="LOCAL_INVENTORY_PACKAGE_TOO_LARGE",
            detail=f"Package exceeds configured {max_bytes} byte limit",
        )
    return content


@router.post(
    "/{inventory_id}/local-inventory-packages/preview",
    response_model=LocalInventoryPackageResponse,
    summary="Validate and stage a local inventory ZIP package",
    description=(
        "Accepts multipart field `file` or raw ZIP bytes. Validates manifest.json, "
        "results.csv, and per-photo checksums. Stages CSV import + photo files. "
        "No productive results or source_assets until confirm."
    ),
)
async def preview_local_inventory_package(
    inventory_id: str,
    request: Request,
    _principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: PreviewLocalInventoryPackage = Depends(
        get_preview_local_inventory_package_use_case
    ),
) -> LocalInventoryPackageResponse:
    settings = load_settings()
    if not getattr(settings, "server_local_inventory_package_enabled", False):
        _raise_package_error(LocalInventoryPackageDisabledError())
    max_bytes = int(getattr(settings, "server_local_inventory_package_max_bytes", 200 * 1024 * 1024))
    content = await _read_zip_request(request, max_bytes)
    try:
        return _response(use_case.execute(inventory_id=inventory_id, content=content))
    except LocalInventoryPackageDisabledError as exc:
        _raise_package_error(exc)
    except LocalInventoryPackageImportError as exc:
        _raise_package_error(exc)
    raise AssertionError("unreachable")


@router.post(
    "/{inventory_id}/local-inventory-packages/confirm",
    response_model=LocalInventoryPackageResponse,
)
def confirm_local_inventory_package(
    inventory_id: str,
    body: ConfirmLocalInventoryPackageRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ConfirmLocalInventoryPackage = Depends(
        get_confirm_local_inventory_package_use_case
    ),
) -> LocalInventoryPackageResponse:
    try:
        record, duplicate = use_case.execute(
            inventory_id=inventory_id,
            export_id=body.export_id,
            conflict_policy=body.conflict_policy,
            confirmed_by_user_id=principal.actor_id or None,
        )
        return _response(record, duplicate=duplicate)
    except LocalInventoryPackageImportError as exc:
        _raise_package_error(exc)
    raise AssertionError("unreachable")


@router.get(
    "/{inventory_id}/local-inventory-packages/{package_id}",
    response_model=LocalInventoryPackageResponse,
)
def get_local_inventory_package(
    inventory_id: str,
    package_id: str,
    _principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: GetLocalInventoryPackage = Depends(get_get_local_inventory_package_use_case),
) -> LocalInventoryPackageResponse:
    try:
        return _response(use_case.execute(inventory_id=inventory_id, package_id=package_id))
    except LocalInventoryPackageImportError as exc:
        _raise_package_error(exc)
    raise AssertionError("unreachable")
