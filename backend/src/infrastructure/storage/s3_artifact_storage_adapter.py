"""
S3-backed artifact storage adapter (Phase 1).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO, Optional

from src.application.ports.services import ArtifactStorage
from src.infrastructure.storage.artifact_store import ArtifactDownload, ArtifactStore, StoredArtifact

logger = logging.getLogger(__name__)


class S3ArtifactStorageAdapter(ArtifactStorage, ArtifactStore):
    """ArtifactStore adapter using boto3 S3 client.

    Key contract:
    - public methods accept logical keys (prefix-free) and also tolerate already-prefixed keys
      for rollout safety and backward compatibility.
    - StoredArtifact.storage_key is always returned as a logical key.
    """

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
        """Return full physical S3 key, idempotently applying configured prefix."""
        raw = (key or "").strip().lstrip("/")
        if not raw:
            raise ValueError("artifact key must not be empty")
        if self._prefix:
            prefix_with_sep = f"{self._prefix}/"
            if raw.startswith(prefix_with_sep):
                return raw
            return f"{self._prefix}/{raw}"
        return raw

    def _client_key(self, key: str) -> str:
        """Normalize caller key (logical or full) to full physical S3 key."""
        return self._object_key(key)

    def _logical_key(self, full_key: str) -> str:
        """Strip configured prefix from a physical key so ``StoredArtifact.storage_key`` stays logical."""
        if self._prefix:
            prefix_with_sep = f"{self._prefix}/"
            if full_key.startswith(prefix_with_sep):
                return full_key[len(prefix_with_sep) :]
        return full_key

    def put_object(self, key: str, file_obj: BinaryIO, content_type: str) -> StoredArtifact:
        object_key = self._client_key(key)
        size: Optional[int] = None
        try:
            cur = file_obj.tell()
            file_obj.seek(0, 2)
            end = file_obj.tell()
            file_obj.seek(cur)
            if isinstance(end, int) and isinstance(cur, int):
                size = max(0, end - cur)
        except Exception:
            size = None
        try:
            result = self._client.upload_fileobj(  # boto3 managed transfer; streaming-safe for large files
                Fileobj=file_obj,
                Bucket=self._bucket,
                Key=object_key,
                ExtraArgs={"ContentType": (content_type or "application/octet-stream")},
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
        etag = None
        if isinstance(result, dict):
            etag = (result.get("ETag") or "").strip('"') or None
        if size is None or etag is None:
            try:
                head = self._client.head_object(Bucket=self._bucket, Key=object_key)
                size = int(head.get("ContentLength") or 0)
                etag = (head.get("ETag") or "").strip('"') or etag
            except Exception:
                # Metadata enrichment is best-effort; keep operation successful.
                if size is None:
                    size = 0
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket=self._bucket,
            storage_key=self._logical_key(object_key),
            content_type=(content_type or "application/octet-stream"),
            file_size_bytes=int(size or 0),
            etag=etag,
        )

    def get_object(self, key: str) -> ArtifactDownload:
        object_key = self._client_key(key)
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

    def object_size_bytes(self, key: str, *, bucket: Optional[str] = None) -> int:
        if bucket and bucket != self._bucket:
            raise RuntimeError(
                f"S3 bucket mismatch for head_object: record_bucket={bucket!r} configured_bucket={self._bucket!r}"
            )
        object_key = self._client_key(key)
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=object_key)
            return int(head.get("ContentLength") or 0)
        except Exception as exc:
            logger.exception("S3 head_object failed bucket=%s key=%s", self._bucket, object_key)
            raise RuntimeError(
                f"S3 head_object failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    def download_to_path(self, key: str, target_path: Path, *, bucket: Optional[str] = None) -> None:
        if bucket and bucket != self._bucket:
            raise RuntimeError(
                f"S3 bucket mismatch for download: record_bucket={bucket!r} configured_bucket={self._bucket!r}"
            )
        object_key = self._client_key(key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(target_path, "wb") as fh:
                self._client.download_fileobj(self._bucket, object_key, fh)
        except Exception as exc:
            logger.exception(
                "S3 download_to_path failed bucket=%s key=%s target=%s",
                self._bucket,
                object_key,
                str(target_path),
            )
            raise RuntimeError(
                f"S3 download_to_path failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    def delete_object(self, key: str) -> None:
        object_key = self._client_key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)
        except Exception as exc:
            logger.exception("S3 delete_object failed bucket=%s key=%s", self._bucket, object_key)
            raise RuntimeError(
                f"S3 delete failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    def object_exists(self, key: str) -> bool:
        object_key = self._client_key(key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=object_key)
            return True
        except Exception:
            return False

    def generate_signed_url(self, key: str, expires_in_sec: int) -> str:
        object_key = self._client_key(key)
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
