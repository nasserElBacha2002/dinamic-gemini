"""Parse FastAPI ``UploadFile`` parts into :class:`UploadedFile` for aisle asset uploads (v3)."""

from __future__ import annotations

from io import BytesIO

from fastapi import HTTPException, UploadFile

from src.api.constants.error_wire import HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED
from src.application.dto.uploaded_file import UploadedFile


async def read_uploaded_files_for_aisle_asset_upload(
    files: list[UploadFile],
) -> list[UploadedFile]:
    """Skip empty parts; 422 if the request has no usable file parts (same rules as the route)."""
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
    return uploaded
