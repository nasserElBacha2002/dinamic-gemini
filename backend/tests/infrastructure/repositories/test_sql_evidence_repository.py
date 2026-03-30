from __future__ import annotations

from types import SimpleNamespace

from src.infrastructure.repositories.sql_evidence_repository import _row_to_evidence


def test_row_to_evidence_prefers_provider_storage_fields() -> None:
    row = SimpleNamespace(
        id="ev-1",
        entity_type="position",
        entity_id="pos-1",
        type="position_crop",
        storage_path="job-a/run/evidence/e1.jpg",
        source_asset_id=None,
        is_primary=True,
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="jobs/job-a/run/evidence/e1.jpg",
        content_type="image/jpeg",
        file_size_bytes=111,
        etag="etag-ev",
        frame_index=1,
        timestamp_ms=12,
        bbox_json=None,
        quality_score=0.9,
    )
    e = _row_to_evidence(row)
    assert e.storage_key == "jobs/job-a/run/evidence/e1.jpg"
    assert e.storage_provider == "s3"
    assert e.storage_bucket == "bucket-a"
    assert e.content_type == "image/jpeg"
    assert e.file_size_bytes == 111
    assert e.etag == "etag-ev"


def test_row_to_evidence_falls_back_to_legacy_storage_path() -> None:
    row = SimpleNamespace(
        id="ev-1",
        entity_type="position",
        entity_id="pos-1",
        type="position_crop",
        storage_path="job-a/run/evidence/e1.jpg",
        source_asset_id=None,
        is_primary=True,
        storage_provider=None,
        storage_bucket=None,
        storage_key=None,
        content_type=None,
        file_size_bytes=None,
        etag=None,
        frame_index=1,
        timestamp_ms=12,
        bbox_json=None,
        quality_score=0.9,
    )
    e = _row_to_evidence(row)
    assert e.storage_key == "job-a/run/evidence/e1.jpg"
    assert e.storage_provider is None
