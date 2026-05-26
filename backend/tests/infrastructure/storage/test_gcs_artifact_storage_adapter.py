from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path

from src.infrastructure.storage.gcs_artifact_storage_adapter import GcsArtifactStorageAdapter


class _FakeGcsBlob:
    def __init__(self, bucket_name: str, name: str, store: dict) -> None:
        self.bucket_name = bucket_name
        self.name = name
        self._store = store
        self.content_type: str | None = None
        self.size: int | None = None
        self.etag: str | None = None

    def upload_from_file(self, file_obj, *, rewind: bool = True, content_type: str | None = None):
        if rewind:
            file_obj.seek(0)
        body = file_obj.read()
        self._store[(self.bucket_name, self.name)] = {
            "body": body,
            "content_type": content_type or "application/octet-stream",
        }
        self.content_type = self._store[(self.bucket_name, self.name)]["content_type"]
        self.size = len(body)
        self.etag = "etag-gcs-1"

    def reload(self) -> None:
        obj = self._store.get((self.bucket_name, self.name))
        if obj is None:
            raise RuntimeError("not found")
        self.size = len(obj["body"])
        self.content_type = obj["content_type"]
        self.etag = "etag-gcs-1"

    def download_as_bytes(self) -> bytes:
        obj = self._store[(self.bucket_name, self.name)]
        self.content_type = obj["content_type"]
        self.size = len(obj["body"])
        return obj["body"]

    def download_to_filename(self, filename: str) -> None:
        Path(filename).write_bytes(self.download_as_bytes())

    def delete(self) -> None:
        self._store.pop((self.bucket_name, self.name), None)

    def exists(self) -> bool:
        return (self.bucket_name, self.name) in self._store

    def generate_signed_url(self, *, version: str, expiration: timedelta, method: str) -> str:
        return (
            f"https://storage.googleapis.com/{self.bucket_name}/{self.name}"
            f"?v={version}&method={method}&ttl={int(expiration.total_seconds())}"
        )


class _FakeGcsBucket:
    def __init__(self, name: str, store: dict) -> None:
        self.name = name
        self._store = store

    def blob(self, name: str) -> _FakeGcsBlob:
        return _FakeGcsBlob(self.name, name, self._store)


class _FakeGcsClient:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict] = {}

    def bucket(self, name: str) -> _FakeGcsBucket:
        return _FakeGcsBucket(name, self._store)


def test_gcs_adapter_put_get_exists_delete_and_signed_url() -> None:
    client = _FakeGcsClient()
    adapter = GcsArtifactStorageAdapter(
        bucket="bucket-gcs",
        prefix="v3",
        project_id="proj-1",
        signed_url_ttl_sec=600,
        storage_client=client,
    )
    stored = adapter.put_object("a/b.txt", BytesIO(b"hello"), "text/plain")
    assert stored.storage_provider == "gcs"
    assert stored.storage_bucket == "bucket-gcs"
    assert stored.storage_key == "a/b.txt"
    assert stored.file_size_bytes == 5
    assert stored.etag == "etag-gcs-1"

    assert adapter.object_exists("a/b.txt") is True
    got = adapter.get_object("a/b.txt")
    assert got.content == b"hello"
    assert got.content_type == "text/plain"
    assert got.file_size_bytes == 5

    url = adapter.generate_signed_url("a/b.txt", expires_in_sec=120)
    assert "bucket-gcs/v3/a/b.txt" in url
    assert "ttl=120" in url

    adapter.delete_object("a/b.txt")
    assert adapter.object_exists("a/b.txt") is False


def test_gcs_adapter_delete_round_trip_with_save_file_result() -> None:
    client = _FakeGcsClient()
    adapter = GcsArtifactStorageAdapter(
        bucket="bucket-gcs",
        prefix="v3",
        storage_client=client,
    )
    key = adapter.save_file("nested/c.txt", BytesIO(b"abc"), "text/plain")
    assert key == "nested/c.txt"
    adapter.delete_file(key)
    assert adapter.object_exists(key) is False


def test_gcs_adapter_generate_signed_url_accepts_already_prefixed_key_without_double_prefix() -> (
    None
):
    client = _FakeGcsClient()
    adapter = GcsArtifactStorageAdapter(
        bucket="bucket-gcs",
        prefix="v3",
        storage_client=client,
    )
    url = adapter.generate_signed_url(
        "v3/inventories/inv-1/visual_references/r1.jpg", expires_in_sec=120
    )
    assert "bucket-gcs/v3/inventories/inv-1/visual_references/r1.jpg" in url
    assert "bucket-gcs/v3/v3/inventories" not in url


def test_gcs_adapter_download_to_path_creates_parent_dirs_and_writes(tmp_path: Path) -> None:
    client = _FakeGcsClient()
    adapter = GcsArtifactStorageAdapter(
        bucket="bucket-gcs",
        prefix="v3",
        storage_client=client,
    )
    adapter.put_object("uploads/aisles/a1/raw/asset.jpg", BytesIO(b"hello-world"), "image/jpeg")
    out = tmp_path / "nested" / "asset.jpg"
    adapter.download_to_path("uploads/aisles/a1/raw/asset.jpg", out, bucket="bucket-gcs")
    assert out.read_bytes() == b"hello-world"
