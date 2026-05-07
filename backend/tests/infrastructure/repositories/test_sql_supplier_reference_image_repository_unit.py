from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.infrastructure.repositories.sql_supplier_reference_image_repository import (
    _row_to_supplier_reference_image,
)


def test_row_to_supplier_reference_image_prefers_provider_metadata() -> None:
    row = SimpleNamespace(
        id="img-1",
        client_supplier_id="sup-1",
        filename="front.png",
        storage_path="client_suppliers/sup-1/reference_images/img-1.png",
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="client_suppliers/sup-1/reference_images/img-1.png",
        content_type="image/png",
        file_size_bytes=2048,
        etag="etag-1",
        mime_type="image/png",
        file_size=2048,
        label="front",
        description="front label",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    image = _row_to_supplier_reference_image(row)
    assert image.storage_provider == "s3"
    assert image.storage_bucket == "bucket-a"
    assert image.storage_key == "client_suppliers/sup-1/reference_images/img-1.png"
    assert image.label == "front"
    assert image.description == "front label"


def test_row_to_supplier_reference_image_falls_back_to_legacy_values() -> None:
    row = SimpleNamespace(
        id="img-1",
        client_supplier_id="sup-1",
        filename="front.png",
        storage_path="client_suppliers/sup-1/reference_images/img-1.png",
        storage_provider=None,
        storage_bucket=None,
        storage_key=None,
        content_type=None,
        file_size_bytes=None,
        etag=None,
        mime_type="image/png",
        file_size=123,
        label=None,
        description=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    image = _row_to_supplier_reference_image(row)
    assert image.storage_key == "client_suppliers/sup-1/reference_images/img-1.png"
    assert image.content_type == "image/png"
    assert image.file_size_bytes == 123
