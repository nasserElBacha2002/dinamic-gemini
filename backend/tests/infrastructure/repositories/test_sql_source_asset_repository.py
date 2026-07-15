"""
Unit tests for SqlSourceAssetRepository — timestamp guard and behavior.

Does not require a real DB; uses mocks to assert save() validates uploaded_at before SQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pyodbc
import pytest

from src.application.errors import DuplicateUploadIdempotencyKeyError
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.repositories.sql_source_asset_repository import (
    SqlSourceAssetRepository,
    _row_to_asset,
)


def _asset(**overrides: object) -> SourceAsset:
    fields: dict[str, object] = dict(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="f.jpg",
        storage_path="aisles/aisle-1/raw/asset-1_f.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
    )
    fields.update(overrides)
    return SourceAsset(**fields)


def test_save_raises_when_uploaded_at_is_none() -> None:
    """uploaded_at is required; raise before any SQL execution."""
    client = MagicMock()
    repo = SqlSourceAssetRepository(client)
    asset = SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="f.jpg",
        storage_path="aisles/aisle-1/raw/asset-1_f.jpg",
        mime_type="image/jpeg",
        uploaded_at=None,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="uploaded_at is required"):
        repo.save(asset)
    client.cursor.assert_not_called()


def test_row_to_asset_prefers_provider_storage_key_when_present() -> None:
    row = SimpleNamespace(
        id="asset-1",
        aisle_id="aisle-1",
        type="photo",
        original_filename="img.jpg",
        storage_path="aisles/aisle-1/raw/legacy.jpg",
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="uploads/aisles/aisle-1/raw/object.jpg",
        content_type="image/jpeg",
        file_size_bytes=1234,
        etag="abc123",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        metadata_json=None,
    )
    asset = _row_to_asset(row)
    assert asset.storage_path == "aisles/aisle-1/raw/legacy.jpg"
    assert asset.storage_key == "uploads/aisles/aisle-1/raw/object.jpg"
    assert asset.storage_provider == "s3"
    assert asset.storage_bucket == "bucket-a"
    assert asset.content_type == "image/jpeg"
    assert asset.file_size_bytes == 1234
    assert asset.etag == "abc123"


def test_row_to_asset_falls_back_to_legacy_storage_path() -> None:
    row = SimpleNamespace(
        id="asset-1",
        aisle_id="aisle-1",
        type="photo",
        original_filename="img.jpg",
        storage_path="aisles/aisle-1/raw/legacy.jpg",
        storage_provider=None,
        storage_bucket=None,
        storage_key=None,
        content_type=None,
        file_size_bytes=None,
        etag=None,
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        metadata_json=None,
    )
    asset = _row_to_asset(row)
    assert asset.storage_key == "aisles/aisle-1/raw/legacy.jpg"
    assert asset.content_type == "image/jpeg"


def test_save_raises_duplicate_upload_idempotency_key_error_on_unique_index_violation() -> None:
    """INSERT hitting UQ_source_assets_aisle_upload_batch_client must surface as the domain
    DuplicateUploadIdempotencyKeyError, not a raw pyodbc.IntegrityError."""
    client = MagicMock()
    cur = MagicMock()
    cur.rowcount = 0  # UPDATE affected no rows -> falls through to INSERT
    cur.execute.side_effect = [
        None,  # UPDATE
        pyodbc.IntegrityError(
            "23000",
            "[23000] [Microsoft][ODBC SQL Server Driver][SQL Server]Violation of UNIQUE KEY "
            "constraint 'UQ_source_assets_aisle_upload_batch_client'. Cannot insert duplicate "
            "key in object 'dbo.source_assets'.",
        ),
    ]
    client.cursor.return_value.__enter__.return_value = cur
    repo = SqlSourceAssetRepository(client)
    asset = _asset(upload_batch_id="batch-1", upload_client_file_id="client-1")

    with pytest.raises(DuplicateUploadIdempotencyKeyError):
        repo.save(asset)

    assert cur.execute.call_count == 2


def test_save_reraises_unrelated_integrity_error_unchanged() -> None:
    """An IntegrityError not matching the idempotency unique index must propagate as-is."""
    client = MagicMock()
    cur = MagicMock()
    cur.rowcount = 0
    cur.execute.side_effect = [
        None,
        pyodbc.IntegrityError("23000", "FOREIGN KEY constraint 'FK_source_assets_aisle' failed."),
    ]
    client.cursor.return_value.__enter__.return_value = cur
    repo = SqlSourceAssetRepository(client)
    asset = _asset()

    with pytest.raises(pyodbc.IntegrityError):
        repo.save(asset)
