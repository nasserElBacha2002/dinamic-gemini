"""``client_file_ids`` / ``upload_batch_id`` validation for multipart upload parsing.

Covers the shared reader used by all three upload endpoints (aisle assets, capture-session
staging, aisle-scoped capture-session staging): strict count matching (no silent None
padding), UUID-shape validation, and max length.
"""

from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.api.errors.structured_api_http import (
    CLIENT_FILE_ID_INVALID,
    CLIENT_FILE_IDS_MISMATCH,
    UPLOAD_BATCH_ID_INVALID,
    StructuredApiHttpError,
)
from src.api.services.multipart_aisle_uploads import read_spooled_multipart_upload_files
from src.application.services.upload_request_limits import UploadRequestLimitPolicy

_VALID_UUID_A = "11111111-1111-1111-1111-111111111111"
_VALID_UUID_B = "22222222-2222-2222-2222-222222222222"
_POLICY = UploadRequestLimitPolicy(
    max_files_per_request=10,
    max_file_size_bytes=10 * 1024 * 1024,
    max_request_size_bytes=10 * 1024 * 1024,
)


def _upload_file(name: str, data: bytes, content_type: str = "image/jpeg") -> UploadFile:
    return UploadFile(
        BytesIO(data),
        filename=name,
        headers=Headers({"content-type": content_type}),
    )


def test_client_file_ids_count_mismatch_is_rejected() -> None:
    files = [_upload_file("a.jpg", b"a"), _upload_file("b.jpg", b"b")]
    with pytest.raises(StructuredApiHttpError) as exc_info:
        asyncio.run(
            read_spooled_multipart_upload_files(
                files,
                client_file_ids=[_VALID_UUID_A],  # only 1 id for 2 files
                policy=_POLICY,
            )
        )
    assert exc_info.value.error_code == CLIENT_FILE_IDS_MISMATCH
    assert exc_info.value.status_code == 422


def test_client_file_ids_too_many_is_rejected() -> None:
    files = [_upload_file("a.jpg", b"a")]
    with pytest.raises(StructuredApiHttpError) as exc_info:
        asyncio.run(
            read_spooled_multipart_upload_files(
                files,
                client_file_ids=[_VALID_UUID_A, _VALID_UUID_B],  # 2 ids for 1 file
                policy=_POLICY,
            )
        )
    assert exc_info.value.error_code == CLIENT_FILE_IDS_MISMATCH


def test_client_file_id_invalid_format_is_rejected() -> None:
    files = [_upload_file("a.jpg", b"a")]
    with pytest.raises(StructuredApiHttpError) as exc_info:
        asyncio.run(
            read_spooled_multipart_upload_files(
                files,
                client_file_ids=["not-a-uuid"],
                policy=_POLICY,
            )
        )
    assert exc_info.value.error_code == CLIENT_FILE_ID_INVALID


def test_client_file_id_too_long_is_rejected() -> None:
    files = [_upload_file("a.jpg", b"a")]
    with pytest.raises(StructuredApiHttpError) as exc_info:
        asyncio.run(
            read_spooled_multipart_upload_files(
                files,
                client_file_ids=["x" * 65],
                policy=_POLICY,
            )
        )
    assert exc_info.value.error_code == CLIENT_FILE_ID_INVALID


def test_upload_batch_id_invalid_format_is_rejected() -> None:
    files = [_upload_file("a.jpg", b"a")]
    with pytest.raises(StructuredApiHttpError) as exc_info:
        asyncio.run(
            read_spooled_multipart_upload_files(
                files,
                upload_batch_id="not-a-uuid",
                policy=_POLICY,
            )
        )
    assert exc_info.value.error_code == UPLOAD_BATCH_ID_INVALID


def test_valid_client_file_ids_and_batch_id_are_parsed_and_assigned_per_file() -> None:
    files = [_upload_file("a.jpg", b"a"), _upload_file("b.jpg", b"b")]
    uploaded = asyncio.run(
        read_spooled_multipart_upload_files(
            files,
            client_file_ids=[_VALID_UUID_A, _VALID_UUID_B],
            upload_batch_id=_VALID_UUID_A,
            policy=_POLICY,
        )
    )
    try:
        assert [uf.client_file_id for uf in uploaded] == [_VALID_UUID_A, _VALID_UUID_B]
        assert all(uf.upload_batch_id == _VALID_UUID_A for uf in uploaded)
    finally:
        for uf in uploaded:
            uf.file_obj.close()


def test_comma_separated_single_field_client_file_ids_is_supported() -> None:
    """Frontends may send ``client_file_ids`` as one comma-separated form field instead of
    repeated fields — both shapes must parse to the same per-file ids."""
    files = [_upload_file("a.jpg", b"a"), _upload_file("b.jpg", b"b")]
    uploaded = asyncio.run(
        read_spooled_multipart_upload_files(
            files,
            client_file_ids=[f"{_VALID_UUID_A},{_VALID_UUID_B}"],
            policy=_POLICY,
        )
    )
    try:
        assert [uf.client_file_id for uf in uploaded] == [_VALID_UUID_A, _VALID_UUID_B]
    finally:
        for uf in uploaded:
            uf.file_obj.close()


def test_missing_client_file_ids_is_legacy_compatible_with_no_idempotency_tracking() -> None:
    files = [_upload_file("a.jpg", b"a")]
    uploaded = asyncio.run(
        read_spooled_multipart_upload_files(files, client_file_ids=None, policy=_POLICY)
    )
    try:
        assert uploaded[0].client_file_id is None
    finally:
        for uf in uploaded:
            uf.file_obj.close()
