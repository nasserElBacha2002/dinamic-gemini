"""Parse FastAPI ``UploadFile`` parts into :class:`UploadedFile` for aisle asset uploads (v3)."""

from __future__ import annotations

from io import BytesIO
from typing import BinaryIO, cast

from fastapi import HTTPException, UploadFile

from src.api.constants.error_wire import HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED
from src.application.dto.uploaded_file import UploadedFile
from src.application.services.upload_request_limits import (
    UploadFileTooLargeError,
    UploadRequestLimitPolicy,
    UploadRequestTooLargeError,
    assert_file_count,
    assert_request_total_size,
)
from src.application.services.upload_stream_io import close_quietly, spool_upload_to_tempfile
from src.config import load_settings


def _parse_client_file_ids(
    *,
    values: list[str] | None,
    file_count: int,
) -> list[str | None]:
    if not values:
        return [None] * file_count
    if len(values) == 1 and "," in values[0]:
        parts = [(p or "").strip() or None for p in values[0].split(",")]
    else:
        parts = [(v or "").strip() or None for v in values]
    if len(parts) < file_count:
        parts.extend([None] * (file_count - len(parts)))
    return parts[:file_count]


async def read_spooled_multipart_upload_files(
    files: list[UploadFile],
    *,
    upload_batch_id: str | None = None,
    client_file_ids: list[str] | None = None,
    policy: UploadRequestLimitPolicy | None = None,
    require_usable: bool = True,
) -> list[UploadedFile]:
    """Spool multipart file parts with size/count policy enforcement."""
    limit_policy = policy or UploadRequestLimitPolicy.from_settings(load_settings())
    assert_file_count(len(files), limit_policy)
    if not files and require_usable:
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED)

    usable: list[UploadFile] = []
    for u in files:
        if not u.filename and not getattr(u, "content_type", None):
            continue
        usable.append(u)
    if not usable and require_usable:
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED)

    client_ids = _parse_client_file_ids(
        values=client_file_ids,
        file_count=len(usable),
    )
    batch_id = (upload_batch_id or "").strip() or None

    uploaded: list[UploadedFile] = []
    total_bytes = 0
    try:
        for idx, u in enumerate(usable):
            try:
                # Prefer Starlette's underlying spool/file handle over buffering into BytesIO.
                source = getattr(u, "file", None) or BytesIO(await u.read())
                spooled, size, _digest = spool_upload_to_tempfile(
                    source,
                    max_file_bytes=limit_policy.max_file_size_bytes,
                )
            except ValueError as exc:
                raise UploadFileTooLargeError(str(exc)) from exc
            total_bytes += size
            assert_request_total_size(total_bytes, limit_policy)
            uploaded.append(
                UploadedFile(
                    original_filename=u.filename or "file",
                    file_obj=cast(BinaryIO, spooled),
                    content_type=u.content_type or "application/octet-stream",
                    client_file_id=client_ids[idx],
                    upload_batch_id=batch_id,
                    size_bytes=size,
                )
            )
    except (UploadFileTooLargeError, UploadRequestTooLargeError):
        for uf in uploaded:
            close_quietly(uf.file_obj)
        raise

    return uploaded


async def read_uploaded_files_for_aisle_asset_upload(
    files: list[UploadFile],
    *,
    upload_batch_id: str | None = None,
    client_file_ids: list[str] | None = None,
) -> list[UploadedFile]:
    """Skip empty parts; 422 if the request has no usable file parts (same rules as the route)."""
    return await read_spooled_multipart_upload_files(
        files,
        upload_batch_id=upload_batch_id,
        client_file_ids=client_file_ids,
        require_usable=True,
    )
