from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.storage.artifact_storage_maintenance import (
    build_local_safe_roots,
    cleanup_local_roots,
    delete_gcs_objects,
    list_gcs_objects,
    run_remote_cleanup,
)


class _FakeBlob:
    def __init__(self, name: str, size: int) -> None:
        self.name = name
        self.size = size
        self.deleted = False

    def delete(self) -> None:
        self.deleted = True


class _FakeBucket:
    def __init__(self, blobs: dict[str, _FakeBlob]) -> None:
        self._blobs = blobs

    def list_blobs(self, *, prefix: str):
        for name, blob in self._blobs.items():
            if name.startswith(prefix):
                yield blob

    def blob(self, name: str) -> _FakeBlob:
        return self._blobs[name]


class _FakeGcsClient:
    def __init__(self, blobs: dict[str, _FakeBlob]) -> None:
        self._blobs = blobs

    def bucket(self, name: str) -> _FakeBucket:
        return _FakeBucket(self._blobs)


class _FakeGcsStore:
    def __init__(self, client: _FakeGcsClient) -> None:
        self._client = client
        self.bucket = "bucket-a"


def test_list_gcs_objects_only_under_prefix() -> None:
    client = _FakeGcsClient(
        {
            "v3/a.jpg": _FakeBlob("v3/a.jpg", 10),
            "v3/nested/b.jpg": _FakeBlob("v3/nested/b.jpg", 20),
            "other/c.jpg": _FakeBlob("other/c.jpg", 5),
        }
    )
    objs = list_gcs_objects(storage_client=client, bucket_name="bucket-a", prefix="v3")
    keys = {o.key for o in objs}
    assert keys == {"v3/a.jpg", "v3/nested/b.jpg"}


def test_delete_gcs_objects_dry_run_does_not_delete() -> None:
    blobs = {"v3/a.jpg": _FakeBlob("v3/a.jpg", 10)}
    client = _FakeGcsClient(blobs)
    objs = list_gcs_objects(storage_client=client, bucket_name="bucket-a", prefix="v3")
    deleted, _, _ = delete_gcs_objects(
        storage_client=client, bucket_name="bucket-a", objects=objs, dry_run=True
    )
    assert deleted == 0
    assert blobs["v3/a.jpg"].deleted is False


def test_run_remote_cleanup_refuses_empty_prefix() -> None:
    store = _FakeGcsStore(_FakeGcsClient({}))
    section = run_remote_cleanup(
        provider="gcs",
        artifact_store=store,
        prefix="",
        bucket="bucket-a",
        dry_run=True,
    )
    assert section.skipped is True
    assert "prefix" in (section.skip_reason or "").lower()


def test_local_cleanup_only_under_v3_uploads(tmp_path: Path) -> None:
    output = tmp_path / "output"
    uploads = output / "v3_uploads" / "uploads" / "x.jpg"
    uploads.parent.mkdir(parents=True)
    uploads.write_bytes(b"abc")
    (output / "other.txt").write_bytes(b"zzz")

    roots = build_local_safe_roots(output_dir=str(output), include_pipeline_temp=False)
    assert len(roots) == 1
    ff, bf, fd, bd, errors = cleanup_local_roots(roots=roots, dry_run=False)
    assert errors == []
    assert ff == 1
    assert fd == 1
    assert not uploads.exists()
    assert (output / "other.txt").exists()


def test_build_local_safe_roots_rejects_unsafe_output_dir() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        build_local_safe_roots(output_dir="/", include_pipeline_temp=False)
