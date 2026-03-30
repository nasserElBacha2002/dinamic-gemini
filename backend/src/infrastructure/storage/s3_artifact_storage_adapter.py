"""
S3-backed artifact storage adapter (Phase 1).
"""

from __future__ import annotations

import logging
from typing import BinaryIO, Optional

from src.application.ports.services import ArtifactStorage
from src.infrastructure.storage.artifact_store import ArtifactDownload, ArtifactStore, StoredArtifact

logger = logging.getLogger(__name__)


class S3ArtifactStorageAdapter(ArtifactStorage, ArtifactStore):
    """ArtifactStore adapter using boto3 S3 client."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        region: Optional[str] = None,
        signed_url_ttl_sec: int = 900,
        s3_client=None,
    ) -> None:
        self._bucket = (bucket or "").strip()
        self._prefix = (prefix or "").strip().strip("/")
        self._region = (region or "").strip() or None
        self._signed_url_ttl_sec = int(signed_url_ttl_sec)
        if self._signed_url_ttl_sec <= 0:
            self._signed_url_ttl_sec = 900
        if s3_client is None:
            try:
                import boto3
            except Exception as exc:  # pragma: no cover - exercised in runtime env
                raise RuntimeError(
                    "boto3 is required for S3 artifact storage adapter; install dependency first"
                ) from exc
            if self._region:
                s3_client = boto3.client("s3", region_name=self._region)
            else:
                s3_client = boto3.client("s3")
        self._client = s3_client

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def prefix(self) -> str:
        return self._prefix

    def _object_key(self, key: str) -> str:
        raw = (key or "").strip().lstrip("/")
        if not raw:
            raise ValueError("artifact key must not be empty")
        if self._prefix:
            return f"{self._prefix}/{raw}"
        return raw

    def put_object(self, key: str, file_obj: BinaryIO, content_type: str) -> StoredArtifact:
        object_key = self._object_key(key)
        payload = file_obj.read()
        size = len(payload)
        try:
            result = self._client.put_object(
                Bucket=self._bucket,
                Key=object_key,
                Body=payload,
                ContentType=(content_type or "application/octet-stream"),
            )
        except Exception as exc:
            logger.exception(
                "S3 put_object failed bucket=%s key=%s size=%s",
                self._bucket,
                object_key,
                size,
            )
            raise RuntimeError(
                f"S3 upload failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc
        etag = (result.get("ETag") or "").strip('"') or None
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket=self._bucket,
            storage_key=object_key,
            content_type=(content_type or "application/octet-stream"),
            file_size_bytes=size,
            etag=etag,
        )

    def get_object(self, key: str) -> ArtifactDownload:
        object_key = self._object_key(key)
        try:
            result = self._client.get_object(Bucket=self._bucket, Key=object_key)
            body = result["Body"].read()
        except Exception as exc:
            logger.exception("S3 get_object failed bucket=%s key=%s", self._bucket, object_key)
            raise RuntimeError(
                f"S3 download failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc
        return ArtifactDownload(
            content=body,
            content_type=(result.get("ContentType") or "application/octet-stream"),
            file_size_bytes=int(result.get("ContentLength") or len(body)),
            etag=(result.get("ETag") or "").strip('"') or None,
        )

    def delete_object(self, key: str) -> None:
        object_key = self._object_key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)
        except Exception as exc:
            logger.exception("S3 delete_object failed bucket=%s key=%s", self._bucket, object_key)
            raise RuntimeError(
                f"S3 delete failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    def object_exists(self, key: str) -> bool:
        object_key = self._object_key(key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=object_key)
            return True
        except Exception:
            return False

    def generate_signed_url(self, key: str, expires_in_sec: int) -> str:
        object_key = self._object_key(key)
        ttl = int(expires_in_sec or self._signed_url_ttl_sec)
        if ttl <= 0:
            ttl = self._signed_url_ttl_sec
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=ttl,
            )
        except Exception as exc:
            logger.exception(
                "S3 generate_presigned_url failed bucket=%s key=%s ttl=%s",
                self._bucket,
                object_key,
                ttl,
            )
            raise RuntimeError(
                f"S3 signed URL generation failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    # Backward-compatible application port methods
    def save_file(self, path: str, file_obj: BinaryIO, content_type: str) -> str:
        stored = self.put_object(path, file_obj, content_type)
        return stored.storage_key

    def delete_file(self, path: str) -> None:
        self.delete_object(path)
