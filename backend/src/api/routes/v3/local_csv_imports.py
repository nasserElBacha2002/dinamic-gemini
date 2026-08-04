"""v3 local CSV inventory import endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.datastructures import UploadFile

from src.api.dependencies import (
    get_confirm_local_csv_import_use_case,
    get_get_local_csv_import_use_case,
    get_preview_local_csv_import_use_case,
)
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.local_csv_import_schemas import (
    ConfirmLocalCsvImportRequest,
    LocalCsvImportResponse,
    LocalCsvImportRowResponse,
)
from src.application.services.local_csv_parser import LocalCsvDocumentError
from src.application.use_cases.inventories.manage_local_csv_import import (
    LOCAL_CSV_EXPORT_CONFLICT,
    LOCAL_CSV_IMPORT_DISABLED,
    LOCAL_CSV_IMPORT_NOT_FOUND,
    LOCAL_CSV_SECONDARY_CONFLICT,
    ConfirmLocalCsvImport,
    GetLocalCsvImport,
    LocalCsvImportDisabledError,
    LocalCsvImportError,
    PreviewLocalCsvImport,
)
from src.config import load_settings
from src.domain.local_csv_import.entities import LocalCsvImport

router = APIRouter()


def _response(record: LocalCsvImport, *, duplicate: bool = False) -> LocalCsvImportResponse:
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
                source="LOCAL_CSV_IMPORT",
                requires_review=row.requires_review,
                error_code=row.error_code,
                notes=row.notes,
                status=row.status,
                validation_errors=list(row.validation_errors),
                validation_warnings=list(row.validation_warnings),
            )
            for row in record.rows
        ],
    )


def _raise_import_error(exc: LocalCsvImportError) -> None:
    status = 422
    if exc.code in {LOCAL_CSV_IMPORT_DISABLED, LOCAL_CSV_IMPORT_NOT_FOUND, "INVENTORY_NOT_FOUND"}:
        status = 404
    elif exc.code in {LOCAL_CSV_EXPORT_CONFLICT, LOCAL_CSV_SECONDARY_CONFLICT}:
        status = 409
    raise StructuredApiHttpError(status, error_code=exc.code, detail=str(exc)) from exc


async def _read_csv_request(request: Request, max_bytes: int) -> bytes:
    content_type = (request.headers.get("content-type") or "").lower()
    length = request.headers.get("content-length")
    if "multipart/form-data" not in content_type and length:
        try:
            if int(length) > max_bytes:
                raise StructuredApiHttpError(
                    413,
                    error_code="LOCAL_CSV_FILE_TOO_LARGE",
                    detail=f"CSV body exceeds configured {max_bytes} byte limit",
                )
        except ValueError:
            pass
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded = form.get("file")
        if not isinstance(uploaded, UploadFile):
            raise StructuredApiHttpError(
                422,
                error_code="LOCAL_CSV_FILE_REQUIRED",
                detail="Multipart request must contain a file field",
            )
        content = await uploaded.read(max_bytes + 1)
    else:
        content = await request.body()
    if len(content) > max_bytes:
        raise StructuredApiHttpError(
            413,
            error_code="LOCAL_CSV_FILE_TOO_LARGE",
            detail=f"CSV exceeds configured {max_bytes} byte limit",
        )
    return content


@router.post(
    "/{inventory_id}/local-csv-imports/preview",
    response_model=LocalCsvImportResponse,
    summary="Validate and stage a local CSV import",
    description=(
        "Accepts multipart field `file` or a raw UTF-8 CSV body. Formula-like text cells "
        "are neutralized before staging. No source assets or final imported rows are created."
    ),
)
async def preview_local_csv_import(
    inventory_id: str,
    request: Request,
    use_case: PreviewLocalCsvImport = Depends(get_preview_local_csv_import_use_case),
) -> LocalCsvImportResponse:
    settings = load_settings()
    if not settings.server_csv_import_enabled:
        _raise_import_error(LocalCsvImportDisabledError())
    max_bytes = settings.server_csv_import_max_bytes
    content = await _read_csv_request(request, max_bytes)
    try:
        return _response(use_case.execute(inventory_id=inventory_id, content=content))
    except LocalCsvImportDisabledError as exc:
        _raise_import_error(exc)
    except LocalCsvDocumentError as exc:
        raise StructuredApiHttpError(422, error_code=exc.code, detail=str(exc)) from exc
    except LocalCsvImportError as exc:
        _raise_import_error(exc)
    raise AssertionError("unreachable")


@router.post(
    "/{inventory_id}/local-csv-imports/confirm",
    response_model=LocalCsvImportResponse,
)
def confirm_local_csv_import(
    inventory_id: str,
    body: ConfirmLocalCsvImportRequest,
    use_case: ConfirmLocalCsvImport = Depends(get_confirm_local_csv_import_use_case),
) -> LocalCsvImportResponse:
    try:
        record, duplicate = use_case.execute(
            inventory_id=inventory_id,
            export_id=body.export_id,
            conflict_policy=body.conflict_policy,
        )
        return _response(record, duplicate=duplicate)
    except LocalCsvImportError as exc:
        _raise_import_error(exc)
    raise AssertionError("unreachable")


@router.get(
    "/{inventory_id}/local-csv-imports/{import_id}",
    response_model=LocalCsvImportResponse,
)
def get_local_csv_import(
    inventory_id: str,
    import_id: str,
    use_case: GetLocalCsvImport = Depends(get_get_local_csv_import_use_case),
) -> LocalCsvImportResponse:
    try:
        return _response(use_case.execute(inventory_id=inventory_id, import_id=import_id))
    except LocalCsvImportError as exc:
        _raise_import_error(exc)
    raise AssertionError("unreachable")
