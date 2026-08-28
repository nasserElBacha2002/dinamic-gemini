"""v3 Dinamic Scanner TXT import endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.datastructures import UploadFile

from src.api.dependencies import (
    get_confirm_dinamic_scanner_txt_import_use_case,
    get_preview_dinamic_scanner_txt_import_use_case,
    require_inventory_client_scope,
)
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.dinamic_scanner_txt_import_schemas import (
    ConfirmDinamicScannerTxtImportRequest,
    DinamicScannerTxtImportResponse,
)
from src.api.schemas.local_csv_import_schemas import (
    LocalCsvImportResponse,
    LocalCsvImportRowResponse,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.use_cases.inventories.manage_dinamic_scanner_txt_import import (
    ConfirmDinamicScannerTxtImport,
    DinamicScannerTxtConfirmResult,
    DinamicScannerTxtPreviewResult,
    PreviewDinamicScannerTxtImport,
)
from src.config import load_settings
from src.domain.dinamic_scanner_txt.errors import (
    TXT_IMPORT_DISABLED,
    DinamicScannerTxtImportDisabledError,
    DinamicScannerTxtImportError,
)
from src.domain.local_csv_import.entities import LocalCsvImport
from src.domain.local_csv_import.errors import (
    LOCAL_CSV_EXPORT_CONFLICT,
    LOCAL_CSV_SECONDARY_CONFLICT,
)
from src.domain.local_csv_import.sources import (
    INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
    INGESTION_SOURCE_LOCAL_CSV_IMPORT,
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
                ingestion_source=(
                    INGESTION_SOURCE_DINAMIC_SCANNER_TXT
                    if row.ingestion_source == INGESTION_SOURCE_DINAMIC_SCANNER_TXT
                    else INGESTION_SOURCE_LOCAL_CSV_IMPORT
                ),
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
    result: DinamicScannerTxtPreviewResult | DinamicScannerTxtConfirmResult,
    *,
    duplicate: bool = False,
) -> DinamicScannerTxtImportResponse:
    return DinamicScannerTxtImportResponse(
        aisle_code=result.aisle_code,
        aisle_id=result.aisle_id,
        aisle_created=result.aisle_created,
        aisle_will_be_created=result.aisle_will_be_created,
        positions_imported=result.positions_imported,
        products_imported=result.products_imported,
        omitted_records=result.omitted_records,
        parse_warnings=list(result.parse_warnings),
        duplicate=duplicate,
        csv_import=_csv_response(result.csv_import, duplicate=duplicate),
    )


def _raise_txt_error(exc: DinamicScannerTxtImportDisabledError | DinamicScannerTxtImportError) -> None:
    if isinstance(exc, DinamicScannerTxtImportDisabledError):
        raise StructuredApiHttpError(404, error_code=TXT_IMPORT_DISABLED, detail=str(exc)) from exc
    status = 422
    if exc.code in {TXT_IMPORT_DISABLED, "INVENTORY_NOT_FOUND"}:
        status = 404
    elif exc.code in {LOCAL_CSV_EXPORT_CONFLICT, LOCAL_CSV_SECONDARY_CONFLICT}:
        status = 409
    raise StructuredApiHttpError(status, error_code=exc.code, detail=str(exc)) from exc


async def _read_txt_request(request: Request, max_bytes: int) -> tuple[bytes, str | None]:
    content_type = (request.headers.get("content-type") or "").lower()
    length = request.headers.get("content-length")
    if "multipart/form-data" not in content_type and length:
        try:
            if int(length) > max_bytes:
                raise StructuredApiHttpError(
                    413,
                    error_code="DINAMIC_SCANNER_TXT_FILE_TOO_LARGE",
                    detail=f"TXT body exceeds configured {max_bytes} byte limit",
                )
        except ValueError:
            pass
    filename: str | None = None
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded = form.get("file")
        if not isinstance(uploaded, UploadFile):
            raise StructuredApiHttpError(
                422,
                error_code="DINAMIC_SCANNER_TXT_FILE_REQUIRED",
                detail="Multipart request must contain a file field",
            )
        filename = uploaded.filename
        content = await uploaded.read(max_bytes + 1)
    else:
        content = await request.body()
    if len(content) > max_bytes:
        raise StructuredApiHttpError(
            413,
            error_code="DINAMIC_SCANNER_TXT_FILE_TOO_LARGE",
            detail=f"TXT exceeds configured {max_bytes} byte limit",
        )
    return content, filename


@router.post(
    "/{inventory_id}/dinamic-scanner-txt-imports/preview",
    response_model=DinamicScannerTxtImportResponse,
    summary="Validate and stage a Dinamic Scanner TXT aisle export",
)
async def preview_dinamic_scanner_txt_import(
    inventory_id: str,
    request: Request,
    _principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: PreviewDinamicScannerTxtImport = Depends(
        get_preview_dinamic_scanner_txt_import_use_case
    ),
) -> DinamicScannerTxtImportResponse:
    settings = load_settings()
    if not getattr(settings, "server_dinamic_scanner_txt_import_enabled", False):
        _raise_txt_error(DinamicScannerTxtImportDisabledError())
    max_bytes = int(getattr(settings, "server_dinamic_scanner_txt_import_max_bytes", 5 * 1024 * 1024))
    content, filename = await _read_txt_request(request, max_bytes)
    try:
        return _response(
            use_case.execute(
                inventory_id=inventory_id,
                content=content,
                filename=filename,
            )
        )
    except DinamicScannerTxtImportDisabledError as exc:
        _raise_txt_error(exc)
    except DinamicScannerTxtImportError as exc:
        _raise_txt_error(exc)
    raise AssertionError("unreachable")


@router.post(
    "/{inventory_id}/dinamic-scanner-txt-imports/confirm",
    response_model=DinamicScannerTxtImportResponse,
)
def confirm_dinamic_scanner_txt_import(
    inventory_id: str,
    body: ConfirmDinamicScannerTxtImportRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    confirm_use_case: ConfirmDinamicScannerTxtImport = Depends(
        get_confirm_dinamic_scanner_txt_import_use_case
    ),
) -> DinamicScannerTxtImportResponse:
    try:
        result = confirm_use_case.execute(
            inventory_id=inventory_id,
            export_id=body.export_id,
            conflict_policy=body.conflict_policy,
            confirmed_by_user_id=principal.actor_id or None,
        )
        return _response(result, duplicate=result.duplicate)
    except DinamicScannerTxtImportDisabledError as exc:
        _raise_txt_error(exc)
    except DinamicScannerTxtImportError as exc:
        _raise_txt_error(exc)
    raise AssertionError("unreachable")
