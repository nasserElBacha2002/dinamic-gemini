from __future__ import annotations

from io import BytesIO

from src.infrastructure.storage.s3_artifact_storage_adapter import S3ArtifactStorageAdapter


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3Client:
    def __init__(self) -> None:
        self._objects = {}

    def upload_fileobj(self, Fileobj, Bucket: str, Key: str, ExtraArgs: dict):
        body = Fileobj.read()
        self._objects[(Bucket, Key)] = {
            "body": body,
            "content_type": ExtraArgs.get("ContentType") or "application/octet-stream",
            "etag": "etag-1",
        }
        return None

    def get_object(self, Bucket: str, Key: str):
        obj = self._objects[(Bucket, Key)]
        return {
            "Body": _FakeBody(obj["body"]),
            "ContentType": obj["content_type"],
            "ContentLength": len(obj["body"]),
            "ETag": '"etag-1"',
        }

    def delete_object(self, Bucket: str, Key: str):
        self._objects.pop((Bucket, Key), None)
        return {}

    def head_object(self, Bucket: str, Key: str):
        if (Bucket, Key) not in self._objects:
            raise RuntimeError("not found")
        return {}

    def generate_presigned_url(self, op: str, Params: dict, ExpiresIn: int) -> str:
        return f"https://example.test/{Params['Bucket']}/{Params['Key']}?ttl={ExpiresIn}"


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
    # save/put returns logical key (without prefix) for compatibility with existing storage_path usage.
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


def test_s3_adapter_generate_signed_url_accepts_already_prefixed_key_without_double_prefix() -> None:
    s3 = _FakeS3Client()
    adapter = S3ArtifactStorageAdapter(
        bucket="bucket-a",
        prefix="v3",
        s3_client=s3,
    )
    url = adapter.generate_signed_url("v3/inventories/inv-1/visual_references/r1.jpg", expires_in_sec=120)
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
    s3.upload_fileobj(BytesIO(b"abc"), Bucket="bucket-a", Key="v3/uploads/aisles/a1/raw/x.jpg", ExtraArgs={})
    assert adapter.object_exists("v3/uploads/aisles/a1/raw/x.jpg") is True
    adapter.delete_object("v3/uploads/aisles/a1/raw/x.jpg")
    assert adapter.object_exists("v3/uploads/aisles/a1/raw/x.jpg") is False
