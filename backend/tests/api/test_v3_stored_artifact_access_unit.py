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
    resolve_source_asset_image_display,
    resolve_visual_reference_file_response,
)
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from src.infrastructure.storage.sql_storage_fields import resolved_storage_key_for_row
from datetime import datetime, timezone

_DEFAULT_STORE_ACCESS_SETTINGS = {
    "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
    "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
}


def test_resolved_storage_key_never_fills_from_path_when_provider_set() -> None:
    assert (
        resolved_storage_key_for_row(
            storage_provider="s3",
            storage_key_raw="",
            storage_path="legacy/path.jpg",
        )
        is None
    )
    assert (
        resolved_storage_key_for_row(
            storage_provider="s3",
            storage_key_raw="logical/k",
            storage_path="legacy/path.jpg",
        )
        == "logical/k"
    )


def test_resolved_storage_key_legacy_uses_path_when_key_missing() -> None:
    assert (
        resolved_storage_key_for_row(
            storage_provider=None,
            storage_key_raw=None,
            storage_path="uploads/x.jpg",
        )
        == "uploads/x.jpg"
    )


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
        lambda: type(
            "S",
            (),
            {"artifact_s3_signed_url_ttl_sec": 900, **_DEFAULT_STORE_ACCESS_SETTINGS},
        )(),
    )
    resp = resolve_source_asset_file_response(asset, artifact_store=mock_store)
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://example/presigned"


def test_resolve_source_asset_image_display_s3_returns_presigned_url(monkeypatch) -> None:
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
        lambda: type(
            "S",
            (),
            {"artifact_s3_signed_url_ttl_sec": 900, **_DEFAULT_STORE_ACCESS_SETTINGS},
        )(),
    )
    url, need_fetch = resolve_source_asset_image_display(asset, artifact_store=mock_store)
    assert url == "https://example/presigned"
    assert need_fetch is False


def test_resolve_source_asset_image_display_local_requires_authenticated_fetch(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "v3_uploads").mkdir(parents=True, exist_ok=True)
    (tmp_path / "v3_uploads" / "k.jpg").write_bytes(b"x")
    asset = SourceAsset(
        id="a1",
        aisle_id="aisle",
        type=SourceAssetType.PHOTO,
        original_filename="p.jpg",
        storage_path="",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="local",
        storage_bucket=None,
        storage_key="k.jpg",
    )
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                "output_dir": str(tmp_path),
                "artifact_s3_signed_url_ttl_sec": 900,
                **_DEFAULT_STORE_ACCESS_SETTINGS,
            },
        )(),
    )
    store = MagicMock()
    url, need_fetch = resolve_source_asset_image_display(asset, artifact_store=store)
    assert url is None
    assert need_fetch is True


def test_resolve_source_asset_image_display_local_missing_file_raises(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "v3_uploads").mkdir(parents=True, exist_ok=True)
    asset = SourceAsset(
        id="a1",
        aisle_id="aisle",
        type=SourceAssetType.PHOTO,
        original_filename="p.jpg",
        storage_path="",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="local",
        storage_bucket=None,
        storage_key="missing.jpg",
    )
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                "output_dir": str(tmp_path),
                "artifact_s3_signed_url_ttl_sec": 900,
                **_DEFAULT_STORE_ACCESS_SETTINGS,
            },
        )(),
    )
    with pytest.raises(StoredArtifactAccessError) as ei:
        resolve_source_asset_image_display(asset, artifact_store=MagicMock())
    assert ei.value.reason_code == "local_file_missing"


def test_resolve_source_asset_image_display_legacy_raises_when_disabled(monkeypatch) -> None:
    asset = SourceAsset(
        id="a1",
        aisle_id="aisle",
        type=SourceAssetType.PHOTO,
        original_filename="p.jpg",
        storage_path="x/y.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                "output_dir": "/nonexistent-out",
                "artifact_storage_legacy_local_read_enabled": False,
                "artifact_s3_signed_url_ttl_sec": 900,
                **_DEFAULT_STORE_ACCESS_SETTINGS,
            },
        )(),
    )
    with pytest.raises(StoredArtifactAccessError) as ei:
        resolve_source_asset_image_display(asset, artifact_store=MagicMock())
    assert ei.value.reason_code == "legacy_local_disabled"


def test_resolve_source_asset_image_display_legacy_ok_when_file_exists(tmp_path: Path, monkeypatch) -> None:
    rel = Path("inv/a/p.jpg")
    file_path = tmp_path / "v3_uploads" / rel
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"x")
    asset = SourceAsset(
        id="a1",
        aisle_id="aisle",
        type=SourceAssetType.PHOTO,
        original_filename="p.jpg",
        storage_path=str(rel).replace("\\", "/"),
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                "output_dir": str(tmp_path),
                "artifact_storage_legacy_local_read_enabled": True,
                "artifact_s3_signed_url_ttl_sec": 900,
                **_DEFAULT_STORE_ACCESS_SETTINGS,
            },
        )(),
    )
    url, need_fetch = resolve_source_asset_image_display(asset, artifact_store=MagicMock())
    assert url is None
    assert need_fetch is True


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
                **_DEFAULT_STORE_ACCESS_SETTINGS,
            },
        )(),
    )
    with pytest.raises(StoredArtifactAccessError) as ei:
        resolve_source_asset_file_response(asset, artifact_store=mock_store)
    assert ei.value.reason_code == "legacy_local_disabled"


def test_read_execution_log_events_durable(tmp_path: Path, monkeypatch) -> None:
    key = "jobs/j1/run/execution_log.jsonl"
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
            {
                "output_dir": str(tmp_path),
                "artifact_storage_legacy_local_read_enabled": False,
                **_DEFAULT_STORE_ACCESS_SETTINGS,
            },
        )(),
    )
    events = read_execution_log_events_for_job(job, artifact_store=store)
    assert len(events) == 1
    assert events[0]["message"] == "hi"


def test_read_execution_log_durable_uses_download_not_get_object(tmp_path: Path, monkeypatch) -> None:
    """Execution log path streams via download_to_path + temp file (no get_object)."""
    key = "jobs/j2/run/execution_log.jsonl"
    body = b'{"ts":"t","stage":"s","level":"info","message":"dl"}\n'

    class _Store:
        bucket = None

        def __init__(self) -> None:
            self.downloaded: list[str] = []
            self.get_called = 0

        def download_to_path(self, k: str, target_path: Path, *, bucket=None) -> None:
            self.downloaded.append(k)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(body)

        def get_object(self, k: str) -> None:
            self.get_called += 1
            raise AssertionError("get_object should not be used for execution log")

    store = _Store()
    job = Job(
        id="j2",
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
            {
                "output_dir": str(tmp_path),
                "artifact_storage_legacy_local_read_enabled": False,
                **_DEFAULT_STORE_ACCESS_SETTINGS,
            },
        )(),
    )
    events = read_execution_log_events_for_job(job, artifact_store=store)
    assert [key] == store.downloaded
    assert store.get_called == 0
    assert len(events) == 1
    assert events[0]["message"] == "dl"


def test_fetch_json_rejects_from_head_before_get_or_download(monkeypatch) -> None:
    """``object_size_bytes`` over max → 413; no get_object / download_to_path."""
    from src.api.services.v3_stored_artifact_access import fetch_json_from_durable_meta

    meta = {
        "storage_provider": "local",
        "storage_bucket": None,
        "storage_key": "jobs/j1/run/hybrid_report.json",
        "content_type": "application/json",
        "file_size_bytes": 1024,
        "etag": None,
    }

    class _Store:
        def __init__(self) -> None:
            self.get_calls = 0
            self.download_calls = 0

        def object_size_bytes(self, key: str, *, bucket=None) -> int:
            return 10_000

        def get_object(self, key: str) -> None:
            self.get_calls += 1
            raise AssertionError("get_object should not run when head size exceeds cap")

        def download_to_path(self, key: str, target_path, *, bucket=None) -> None:
            self.download_calls += 1
            raise AssertionError("download_to_path should not run when head size exceeds cap")

    store = _Store()
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                **_DEFAULT_STORE_ACCESS_SETTINGS,
                "artifact_store_max_json_load_bytes": 64,
            },
        )(),
    )
    with pytest.raises(StoredArtifactAccessError) as ei:
        fetch_json_from_durable_meta(meta, artifact_store=store, label="Hybrid report")
    assert ei.value.reason_code == "payload_too_large"
    assert store.get_calls == 0
    assert store.download_calls == 0


def test_fetch_json_when_head_fails_rejects_from_on_disk_stat(monkeypatch) -> None:
    """Size unknown: stream to tempfile, reject when on-disk size exceeds cap (no full read)."""
    from src.api.services.v3_stored_artifact_access import fetch_json_from_durable_meta

    meta = {
        "storage_provider": "local",
        "storage_bucket": None,
        "storage_key": "jobs/j1/run/hybrid_report.json",
        "content_type": "application/json",
        "file_size_bytes": 1,
        "etag": None,
    }

    class _Store:
        def __init__(self) -> None:
            self.download_calls = 0

        def object_size_bytes(self, key: str, *, bucket=None) -> int:
            raise RuntimeError("head unavailable")

        def get_object(self, key: str) -> None:
            raise AssertionError("get_object must not run for unknown-size JSON load")

        def download_to_path(self, key: str, target_path: Path, *, bucket=None) -> None:
            self.download_calls += 1
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(b"x" * 500)

    store = _Store()
    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                **_DEFAULT_STORE_ACCESS_SETTINGS,
                "artifact_store_max_json_load_bytes": 100,
                "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
            },
        )(),
    )
    with pytest.raises(StoredArtifactAccessError) as ei:
        fetch_json_from_durable_meta(meta, artifact_store=store, label="Hybrid report")
    assert ei.value.reason_code == "payload_too_large"
    assert store.download_calls == 1


def test_fetch_json_when_head_fails_loads_when_under_cap(monkeypatch) -> None:
    from src.api.services.v3_stored_artifact_access import fetch_json_from_durable_meta

    meta = {
        "storage_provider": "local",
        "storage_bucket": None,
        "storage_key": "jobs/j1/run/hybrid_report.json",
        "content_type": "application/json",
        "file_size_bytes": 1,
        "etag": None,
    }
    payload = b'{"ok": true}'

    class _Store:
        def object_size_bytes(self, key: str, *, bucket=None) -> int:
            raise RuntimeError("head unavailable")

        def get_object(self, key: str) -> None:
            raise AssertionError("no get_object")

        def download_to_path(self, key: str, target_path: Path, *, bucket=None) -> None:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(payload)

    monkeypatch.setattr(
        "src.api.services.v3_stored_artifact_access.load_settings",
        lambda: type(
            "S",
            (),
            {
                **_DEFAULT_STORE_ACCESS_SETTINGS,
                "artifact_store_max_json_load_bytes": 1024,
            },
        )(),
    )
    out = fetch_json_from_durable_meta(meta, artifact_store=_Store(), label="Hybrid report")
    assert out == {"ok": True}


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
                **_DEFAULT_STORE_ACCESS_SETTINGS,
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
                **_DEFAULT_STORE_ACCESS_SETTINGS,
            },
        )(),
    )
    with pytest.raises(StoredArtifactAccessError) as asset_e:
        resolve_source_asset_file_response(asset, artifact_store=mock_store)
    with pytest.raises(StoredArtifactAccessError) as ref_e:
        resolve_visual_reference_file_response(ref, artifact_store=mock_store)

    assert asset_e.value.reason_code == "incomplete_metadata"
    assert ref_e.value.reason_code == "incomplete_metadata"
