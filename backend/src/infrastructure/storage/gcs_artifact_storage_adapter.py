"""
GCS-backed artifact storage adapter (Phase 1).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

from src.application.ports.services import ArtifactStorage
from src.infrastructure.storage.artifact_store import (
    ArtifactDownload,
    ArtifactStore,
    StoredArtifact,
    StoredObjectMetadata,
)

logger = logging.getLogger(__name__)


class GcsArtifactStorageAdapter(ArtifactStorage, ArtifactStore):
    """ArtifactStore adapter using google-cloud-storage.

    Key contract mirrors :class:`S3ArtifactStorageAdapter`:
    - public methods accept logical keys (no duplication of the configured bucket prefix)
    - ``put_object`` returns ``StoredArtifact.storage_key`` in logical form
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        project_id: str | None = None,
        signed_url_ttl_sec: int = 900,
        storage_client=None,
    ) -> None:
        self._bucket = (bucket or "").strip()
        self._prefix = (prefix or "").strip().strip("/")
        self._project_id = (project_id or "").strip() or None
        self._signed_url_ttl_sec = int(signed_url_ttl_sec)
        if self._signed_url_ttl_sec <= 0:
            self._signed_url_ttl_sec = 900
        if storage_client is None:
            try:
                from google.cloud import storage as gcs_storage
            except Exception as exc:  # pragma: no cover - exercised in runtime env
                raise RuntimeError(
                    "google-cloud-storage is required for GCS artifact storage adapter; "
                    "install dependency first"
                ) from exc
            if self._project_id:
                storage_client = gcs_storage.Client(project=self._project_id)
            else:
                storage_client = gcs_storage.Client()
        self._client = storage_client

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def prefix(self) -> str:
        return self._prefix

    def _gcs_bucket(self):
        return self._client.bucket(self._bucket)

    def _object_key(self, key: str) -> str:
        """Return full physical GCS object name, idempotently applying configured prefix."""
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
        return self._object_key(key)

    def _logical_key(self, full_key: str) -> str:
        if self._prefix:
            prefix_with_sep = f"{self._prefix}/"
            if full_key.startswith(prefix_with_sep):
                return full_key[len(prefix_with_sep) :]
        return full_key

    def _blob(self, key: str):
        object_key = self._client_key(key)
        return self._gcs_bucket().blob(object_key), object_key

    def put_object(self, key: str, file_obj: BinaryIO, content_type: str) -> StoredArtifact:
        blob, object_key = self._blob(key)
        stream_size: int | None = None
        try:
            cur = file_obj.tell()
            file_obj.seek(0, 2)
            end = file_obj.tell()
            file_obj.seek(cur)
            if isinstance(end, int):
                stream_size = int(end)
        except Exception:
            stream_size = None
        try:
            blob.upload_from_file(
                file_obj,
                rewind=True,
                content_type=(content_type or "application/octet-stream"),
            )
        except Exception as exc:
            logger.exception(
                "GCS put_object failed bucket=%s key=%s stream_size=%s",
                self._bucket,
                object_key,
                stream_size,
            )
            raise RuntimeError(
                f"GCS upload failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc
        size: int | None = stream_size
        etag: str | None = None
        try:
            blob.reload()
            if blob.size is not None:
                size = int(blob.size)
            etag = (blob.etag or "").strip() or None
        except Exception:
            if size is None:
                size = 0
        return StoredArtifact(
            storage_provider="gcs",
            storage_bucket=self._bucket,
            storage_key=self._logical_key(object_key),
            content_type=(content_type or "application/octet-stream"),
            file_size_bytes=int(size or 0),
            etag=etag,
        )

    def get_object(self, key: str) -> ArtifactDownload:
        blob, object_key = self._blob(key)
        try:
            body = blob.download_as_bytes()
            try:
                blob.reload()
            except Exception:
                pass
        except Exception as exc:
            logger.exception("GCS get_object failed bucket=%s key=%s", self._bucket, object_key)
            raise RuntimeError(
                f"GCS download failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc
        content_type = blob.content_type or "application/octet-stream"
        file_size = int(blob.size or len(body))
        etag = (blob.etag or "").strip() or None
        return ArtifactDownload(
            content=body,
            content_type=content_type,
            file_size_bytes=file_size,
            etag=etag,
        )

    def object_size_bytes(self, key: str, *, bucket: str | None = None) -> int:
        if bucket and bucket != self._bucket:
            raise RuntimeError(
                f"GCS bucket mismatch for metadata: record_bucket={bucket!r} "
                f"configured_bucket={self._bucket!r}"
            )
        blob, object_key = self._blob(key)
        try:
            blob.reload()
            return int(blob.size or 0)
        except Exception as exc:
            logger.exception("GCS blob metadata failed bucket=%s key=%s", self._bucket, object_key)
            raise RuntimeError(
                f"GCS metadata failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    def read_range(
        self,
        key: str,
        *,
        start: int,
        length: int,
        bucket: str | None = None,
    ) -> bytes:
        if bucket and bucket != self._bucket:
            raise RuntimeError(
                f"GCS bucket mismatch for read_range: record_bucket={bucket!r} "
                f"configured_bucket={self._bucket!r}"
            )
        if start < 0:
            raise ValueError("start must be >= 0")
        if length < 0:
            raise ValueError("length must be >= 0")
        if length == 0:
            return b""
        blob, object_key = self._blob(key)
        end = start + length - 1
        try:
            return blob.download_as_bytes(start=start, end=end)
        except Exception as exc:
            logger.exception(
                "GCS read_range failed bucket=%s key=%s start=%s length=%s",
                self._bucket,
                object_key,
                start,
                length,
            )
            raise RuntimeError(
                f"GCS ranged read failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    def get_object_metadata(self, key: str, *, bucket: str | None = None) -> StoredObjectMetadata:
        if bucket and bucket != self._bucket:
            raise RuntimeError(
                f"GCS bucket mismatch for metadata: record_bucket={bucket!r} "
                f"configured_bucket={self._bucket!r}"
            )
        blob, object_key = self._blob(key)
        try:
            blob.reload()
        except Exception as exc:
            logger.exception("GCS blob metadata failed bucket=%s key=%s", self._bucket, object_key)
            raise RuntimeError(
                f"GCS metadata failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc
        return StoredObjectMetadata(
            file_size_bytes=int(blob.size or 0),
            etag=(blob.etag or "").strip() or None,
            content_type=blob.content_type or None,
            updated_at=blob.updated or None,
        )

    def download_to_path(self, key: str, target_path: Path, *, bucket: str | None = None) -> None:
        if bucket and bucket != self._bucket:
            raise RuntimeError(
                f"GCS bucket mismatch for download: record_bucket={bucket!r} "
                f"configured_bucket={self._bucket!r}"
            )
        blob, object_key = self._blob(key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            blob.download_to_filename(str(target_path))
        except Exception as exc:
            logger.exception(
                "GCS download_to_path failed bucket=%s key=%s target=%s",
                self._bucket,
                object_key,
                str(target_path),
            )
            raise RuntimeError(
                f"GCS download_to_path failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    def delete_object(self, key: str) -> None:
        from google.api_core.exceptions import NotFound

        blob, object_key = self._blob(key)
        try:
            blob.delete()
        except NotFound:
            logger.info(
                "GCS delete_object no-op (already missing) bucket=%s key=%s",
                self._bucket,
                object_key,
            )
            return
        except Exception as exc:
            logger.exception("GCS delete_object failed bucket=%s key=%s", self._bucket, object_key)
            raise RuntimeError(
                f"GCS delete failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    def object_exists(self, key: str) -> bool:
        blob, _object_key = self._blob(key)
        try:
            return bool(blob.exists())
        except Exception:
            return False

    def generate_signed_url(self, key: str, expires_in_sec: int) -> str:
        blob, object_key = self._blob(key)
        ttl = int(expires_in_sec or self._signed_url_ttl_sec)
        if ttl <= 0:
            ttl = self._signed_url_ttl_sec
        try:
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=ttl),
                method="GET",
            )
            return str(url)
        except Exception as exc:
            logger.exception(
                "GCS generate_signed_url failed bucket=%s key=%s ttl=%s",
                self._bucket,
                object_key,
                ttl,
            )
            raise RuntimeError(
                f"GCS signed URL generation failed for key={object_key!r} bucket={self._bucket!r}"
            ) from exc

    def save_file(self, path: str, file_obj: BinaryIO, content_type: str) -> str:
        stored = self.put_object(path, file_obj, content_type)
        return stored.storage_key

    def delete_file(self, path: str) -> None:
        self.delete_object(path)
