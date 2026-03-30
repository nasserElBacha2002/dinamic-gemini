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

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str):
        self._objects[(Bucket, Key)] = {"body": Body, "content_type": ContentType, "etag": "etag-1"}
        return {"ETag": '"etag-1"'}

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
    assert stored.storage_key == "v3/a/b.txt"
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
