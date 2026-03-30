"""Unit tests for Phase 4 v3_stored_artifact_access (no full HTTP app)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.jobs.entities import Job, JobStatus
from src.api.services.v3_stored_artifact_access import (
    StoredArtifactAccessError,
    read_execution_log_events_for_job,
    resolve_source_asset_file_response,
    resolve_visual_reference_file_response,
)
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from datetime import datetime, timezone


def test_resolve_source_asset_s3_uses_redirect(monkeypatch) -> None:
    asset = SourceAsset(
        id="a1",
        aisle_id="aisle",
        type=SourceAssetType.PHOTO,
        original_filename="p.jpg",
        storage_path="legacy/ignored",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="myb",
        storage_key="k1",
    )
    mock_store = MagicMock()
    mock_store.bucket = "myb"
    mock_store.generate_signed_url.return_value = "https://example/presigned"

    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type("S", (), {"artifact_s3_signed_url_ttl_sec": 900})(),
    )
    resp = resolve_source_asset_file_response(asset, artifact_store=mock_store)
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://example/presigned"


def test_resolve_source_asset_legacy_requires_flag(monkeypatch) -> None:
    asset = SourceAsset(
        id="a1",
        aisle_id="aisle",
        type=SourceAssetType.PHOTO,
        original_filename="p.jpg",
        storage_path="x/y.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
    )
    mock_store = MagicMock()
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                "output_dir": "/nonexistent-out",
                "artifact_storage_legacy_local_read_enabled": False,
            },
        )(),
    )
    with pytest.raises(StoredArtifactAccessError) as ei:
        resolve_source_asset_file_response(asset, artifact_store=mock_store)
    assert ei.value.reason_code == "legacy_local_disabled"


def test_read_execution_log_events_durable(tmp_path: Path, monkeypatch) -> None:
    key = "v3/jobs/j1/run/execution_log.jsonl"
    body = b'{"ts":"t","stage":"s","level":"info","message":"hi"}\n'
    store = V3ArtifactStorageAdapter(tmp_path / "art")
    store.put_object(key, BytesIO(body), "application/x-ndjson")

    job = Job(
        id="j1",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        result_json={
            "durable_artifacts": {
                "execution_log": {
                    "storage_provider": "local",
                    "storage_bucket": None,
                    "storage_key": key,
                    "content_type": "application/x-ndjson",
                    "file_size_bytes": len(body),
                    "etag": None,
                }
            }
        },
    )
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {"output_dir": str(tmp_path), "artifact_storage_legacy_local_read_enabled": False},
        )(),
    )
    events = read_execution_log_events_for_job(job, artifact_store=store)
    assert len(events) == 1
    assert events[0]["message"] == "hi"


def test_visual_reference_incomplete_provider_metadata_fails_without_legacy_fallback(monkeypatch) -> None:
    ref = InventoryVisualReference(
        id="vr1",
        inventory_id="inv1",
        filename="ref.jpg",
        storage_path="legacy/path.jpg",
        mime_type="image/jpeg",
        file_size=100,
        created_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key=None,
    )
    mock_store = MagicMock()
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                "output_dir": "/nonexistent",
                "artifact_storage_legacy_local_read_enabled": True,
                "artifact_s3_signed_url_ttl_sec": 900,
            },
        )(),
    )
    with pytest.raises(StoredArtifactAccessError) as ei:
        resolve_visual_reference_file_response(ref, artifact_store=mock_store)
    assert ei.value.reason_code == "incomplete_metadata"


def test_source_and_visual_reference_incomplete_metadata_are_consistent(monkeypatch) -> None:
    asset = SourceAsset(
        id="a-inc",
        aisle_id="aisle",
        type=SourceAssetType.PHOTO,
        original_filename="a.jpg",
        storage_path="legacy/a.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="",
    )
    ref = InventoryVisualReference(
        id="vr-inc",
        inventory_id="inv",
        filename="r.jpg",
        storage_path="legacy/r.jpg",
        mime_type="image/jpeg",
        file_size=1,
        created_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="",
    )
    mock_store = MagicMock()
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                "output_dir": "/nonexistent",
                "artifact_storage_legacy_local_read_enabled": True,
                "artifact_s3_signed_url_ttl_sec": 900,
            },
        )(),
    )
    with pytest.raises(StoredArtifactAccessError) as asset_e:
        resolve_source_asset_file_response(asset, artifact_store=mock_store)
    with pytest.raises(StoredArtifactAccessError) as ref_e:
        resolve_visual_reference_file_response(ref, artifact_store=mock_store)

    assert asset_e.value.reason_code == "incomplete_metadata"
    assert ref_e.value.reason_code == "incomplete_metadata"
