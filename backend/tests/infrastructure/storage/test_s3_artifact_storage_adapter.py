from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from src.infrastructure.storage.s3_artifact_storage_adapter import S3ArtifactStorageAdapter


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3Client:
    def __init__(self) -> None:
        self._objects = {}

    def upload_fileobj(self, Fileobj, Bucket: str, Key: str, ExtraArgs: dict):  # noqa: N803
        body = Fileobj.read()
        self._objects[(Bucket, Key)] = {
            "body": body,
            "content_type": ExtraArgs.get("ContentType") or "application/octet-stream",
            "etag": "etag-1",
        }
        return None

    def get_object(self, Bucket: str, Key: str, Range: str | None = None):  # noqa: N803
        obj = self._objects[(Bucket, Key)]
        body = obj["body"]
        if Range:
            # Only the ``bytes=start-end`` form is exercised by the adapter under test.
            spec = Range.removeprefix("bytes=")
            start_s, end_s = spec.split("-")
            start, end = int(start_s), int(end_s)
            body = body[start : end + 1]
        return {
            "Body": _FakeBody(body),
            "ContentType": obj["content_type"],
            "ContentLength": len(body),
            "ETag": '"etag-1"',
        }

    def delete_object(self, Bucket: str, Key: str):  # noqa: N803
        self._objects.pop((Bucket, Key), None)
        return {}

    def head_object(self, Bucket: str, Key: str):  # noqa: N803
        if (Bucket, Key) not in self._objects:
            raise RuntimeError("not found")
        obj = self._objects[(Bucket, Key)]
        body = obj["body"]
        return {
            "ContentLength": len(body),
            "ETag": '"etag-1"',
            "ContentType": obj["content_type"],
        }

    def generate_presigned_url(self, op: str, Params: dict, ExpiresIn: int) -> str:  # noqa: N803
        return f"https://example.test/{Params['Bucket']}/{Params['Key']}?ttl={ExpiresIn}"

    def download_fileobj(self, Bucket: str, Key: str, Fileobj):  # noqa: N803
        obj = self._objects[(Bucket, Key)]
        Fileobj.write(obj["body"])


def test_s3_adapter_put_get_exists_delete_and_signed_url() -> None:
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(
        bucket="bucket-a",
        prefix="v3",
        region="us-east-1",
        signed_url_ttl_sec=600,
        s3_client=s3,
    )
    stored = adapter.put_object("a/b.txt", BytesIO(b"hello"), "text/plain")
    assert stored.storage_provider == "s3"
    assert stored.storage_bucket == "bucket-a"
    # StoredArtifact.storage_key is always logical (prefix stripped in adapter).
    assert stored.storage_key == "a/b.txt"
    assert stored.file_size_bytes == 5
    assert stored.etag == "etag-1"

    assert adapter.object_exists("a/b.txt") is True
    got = adapter.get_object("a/b.txt")
    assert got.content == b"hello"
    assert got.content_type == "text/plain"
    assert got.file_size_bytes == 5

    url = adapter.generate_signed_url("a/b.txt", expires_in_sec=120)
    assert "bucket-a/v3/a/b.txt" in url
    assert "ttl=120" in url

    adapter.delete_object("a/b.txt")
    assert adapter.object_exists("a/b.txt") is False


def test_s3_adapter_delete_round_trip_with_save_file_result() -> None:
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(
        bucket="bucket-a",
        prefix="v3",
        s3_client=s3,
    )
    key = adapter.save_file("nested/c.txt", BytesIO(b"abc"), "text/plain")
    assert key == "nested/c.txt"
    # Must not double-prefix when deleting a key previously returned by save_file.
    adapter.delete_file(key)
    assert adapter.object_exists(key) is False


def test_s3_adapter_generate_signed_url_accepts_already_prefixed_key_without_double_prefix() -> (
    None
):
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(
        bucket="bucket-a",
        prefix="v3",
        s3_client=s3,
    )
    url = adapter.generate_signed_url(
        "v3/inventories/inv-1/visual_references/r1.jpg", expires_in_sec=120
    )
    assert "bucket-a/v3/inventories/inv-1/visual_references/r1.jpg" in url
    assert "bucket-a/v3/v3/inventories" not in url


def test_s3_adapter_delete_accepts_already_prefixed_key_without_double_prefix() -> None:
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(
        bucket="bucket-a",
        prefix="v3",
        s3_client=s3,
    )
    # Seed object using full physical key.
    s3.upload_fileobj(
        BytesIO(b"abc"), Bucket="bucket-a", Key="v3/uploads/aisles/a1/raw/x.jpg", ExtraArgs={}
    )
    assert adapter.object_exists("v3/uploads/aisles/a1/raw/x.jpg") is True
    adapter.delete_object("v3/uploads/aisles/a1/raw/x.jpg")
    assert adapter.object_exists("v3/uploads/aisles/a1/raw/x.jpg") is False


def test_s3_adapter_object_size_bytes_matches_uploaded_length() -> None:
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(
        bucket="bucket-a",
        prefix="v3",
        s3_client=s3,
    )
    adapter.put_object("uploads/x.bin", BytesIO(b"abcd"), "application/octet-stream")
    assert adapter.object_size_bytes("uploads/x.bin", bucket="bucket-a") == 4


def test_s3_adapter_read_range_uses_range_header_and_slices_body() -> None:
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(
        bucket="bucket-a",
        prefix="v3",
        s3_client=s3,
    )
    adapter.put_object("uploads/x.bin", BytesIO(b"0123456789"), "application/octet-stream")

    assert adapter.read_range("uploads/x.bin", start=2, length=4, bucket="bucket-a") == b"2345"
    # Length beyond EOF should still return whatever bytes are available.
    assert adapter.read_range("uploads/x.bin", start=8, length=10, bucket="bucket-a") == b"89"
    assert adapter.read_range("uploads/x.bin", start=0, length=0, bucket="bucket-a") == b""


def test_s3_adapter_read_range_rejects_bucket_mismatch() -> None:
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(bucket="bucket-a", prefix="v3", s3_client=s3)
    adapter.put_object("uploads/x.bin", BytesIO(b"abcd"), "application/octet-stream")
    with pytest.raises(RuntimeError, match="bucket mismatch"):
        adapter.read_range("uploads/x.bin", start=0, length=1, bucket="other-bucket")


def test_s3_adapter_get_object_metadata_returns_head_fields() -> None:
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(bucket="bucket-a", prefix="v3", s3_client=s3)
    adapter.put_object("uploads/meta.txt", BytesIO(b"hello"), "text/plain")

    meta = adapter.get_object_metadata("uploads/meta.txt", bucket="bucket-a")
    assert meta.file_size_bytes == 5
    assert meta.etag == "etag-1"
    assert meta.content_type == "text/plain"


def test_s3_adapter_download_to_path_streams_without_get_object_buffering(tmp_path: Path) -> None:
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(
        bucket="bucket-a",
        prefix="v3",
        s3_client=s3,
    )
    adapter.put_object("uploads/aisles/a1/raw/asset.jpg", BytesIO(b"hello-world"), "image/jpeg")
    out = tmp_path / "asset.jpg"
    adapter.download_to_path("uploads/aisles/a1/raw/asset.jpg", out, bucket="bucket-a")
    assert out.read_bytes() == b"hello-world"
