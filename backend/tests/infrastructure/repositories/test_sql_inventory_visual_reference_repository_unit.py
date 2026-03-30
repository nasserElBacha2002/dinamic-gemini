from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.infrastructure.repositories.sql_inventory_visual_reference_repository import _row_to_reference


def test_row_to_reference_prefers_provider_metadata() -> None:
    row = SimpleNamespace(
        id="ref-1",
        inventory_id="inv-1",
        filename="a.png",
        storage_path="inventories/inv-1/visual_references/ref-1.png",
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="inventories/inv-1/visual_references/ref-1.png",
        content_type="image/png",
        file_size_bytes=2048,
        etag="etag-1",
        mime_type="image/png",
        file_size=2048,
        created_at=datetime.now(timezone.utc),
    )
    ref = _row_to_reference(row)
    assert ref.storage_provider == "s3"
    assert ref.storage_bucket == "bucket-a"
    assert ref.storage_key == "inventories/inv-1/visual_references/ref-1.png"
    assert ref.content_type == "image/png"
    assert ref.file_size_bytes == 2048
    assert ref.etag == "etag-1"


def test_row_to_reference_falls_back_to_legacy_values() -> None:
    row = SimpleNamespace(
        id="ref-1",
        inventory_id="inv-1",
        filename="a.png",
        storage_path="inventories/inv-1/visual_references/ref-1.png",
        storage_provider=None,
        storage_bucket=None,
        storage_key=None,
        content_type=None,
        file_size_bytes=None,
        etag=None,
        mime_type="image/png",
        file_size=123,
        created_at=datetime.now(timezone.utc),
    )
    ref = _row_to_reference(row)
    assert ref.storage_key == "inventories/inv-1/visual_references/ref-1.png"
    assert ref.content_type == "image/png"
    assert ref.file_size_bytes == 123
