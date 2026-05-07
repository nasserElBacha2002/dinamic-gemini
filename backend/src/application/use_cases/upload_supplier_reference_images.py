"""Upload/list supplier reference images — Phase C1."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, BinaryIO
from uuid import uuid4

from src.application.errors import (
    ClientNotFoundError,
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
    EmptyUploadError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    ClientRepository,
    ClientSupplierRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.services import ArtifactStorage
from src.application.use_cases.upload_inventory_visual_references import (
    ALLOWED_MIME_TYPES,
    _normalize_mime,
)
from src.application.utils.supplier_reference_image_paths import (
    supplier_reference_image_storage_path,
)
from src.domain.client_supplier.reference_image import SupplierReferenceImage

logger = logging.getLogger(__name__)


@dataclass
class UploadedSupplierReferenceImageFile:
    """Framework-agnostic in-memory upload DTO for supplier reference images."""

    original_filename: str
    file_obj: BinaryIO
    content_type: str
    size: int
    label: str | None = None
    description: str | None = None


class UploadSupplierReferenceImagesUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        reference_repo: SupplierReferenceImageRepository,
        artifact_storage: ArtifactStorage,
        clock: Clock,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._reference_repo = reference_repo
        self._artifact_storage = artifact_storage
        self._clock = clock

    def execute(
        self,
        client_id: str,
        supplier_id: str,
        files: Sequence[UploadedSupplierReferenceImageFile],
    ) -> list[SupplierReferenceImage]:
        if not files:
            raise EmptyUploadError("At least one file is required")
        self._validate_supplier_in_client_scope(client_id=client_id, supplier_id=supplier_id)

        for f in files:
            if f.size <= 0:
                raise ZeroByteFileError("Empty or zero-byte files are not allowed")
            mime = _normalize_mime(f.content_type)
            if mime not in ALLOWED_MIME_TYPES:
                raise UnsupportedAssetTypeError(
                    f"Unsupported image content type for supplier reference image: {f.content_type}"
                )

        now = self._clock.now()
        created: list[SupplierReferenceImage] = []
        written_paths: list[str] = []
        try:
            for f in files:
                mime = _normalize_mime(f.content_type)
                reference_image_id = str(uuid4())
                storage_path = supplier_reference_image_storage_path(
                    client_supplier_id=supplier_id,
                    reference_image_id=reference_image_id,
                    mime_type=mime,
                )
                storage_provider = None
                storage_bucket = None
                storage_key = None
                content_type = mime
                file_size_bytes = f.size
                etag = None
                put_object = getattr(self._artifact_storage, "put_object", None)
                if callable(put_object):
                    stored: Any = put_object(storage_path, f.file_obj, mime)
                    storage_provider = getattr(stored, "storage_provider", None)
                    storage_bucket = getattr(stored, "storage_bucket", None)
                    storage_key = getattr(stored, "storage_key", None)
                    content_type = getattr(stored, "content_type", None) or mime
                    file_size_bytes = int(getattr(stored, "file_size_bytes", f.size) or f.size)
                    etag = getattr(stored, "etag", None)
                else:
                    self._artifact_storage.save_file(storage_path, f.file_obj, mime)
                    storage_key = storage_path

                persisted_key = storage_key or storage_path
                written_paths.append(persisted_key)
                created.append(
                    SupplierReferenceImage(
                        id=reference_image_id,
                        client_supplier_id=supplier_id,
                        filename=f.original_filename or "file",
                        storage_path=storage_path,
                        mime_type=mime,
                        file_size=f.size,
                        created_at=now,
                        updated_at=now,
                        storage_provider=storage_provider,
                        storage_bucket=storage_bucket,
                        storage_key=persisted_key,
                        content_type=content_type,
                        file_size_bytes=file_size_bytes,
                        etag=etag,
                        label=(f.label or "").strip() or None,
                        description=(f.description or "").strip() or None,
                    )
                )
            self._reference_repo.create_many(created)
        except Exception:
            for p in reversed(written_paths):
                try:
                    self._artifact_storage.delete_file(p)
                except Exception as cleanup_error:
                    logger.warning(
                        "Rollback cleanup failed for supplier reference image file %s: %s",
                        p,
                        cleanup_error,
                    )
            raise
        return created

    def _validate_supplier_in_client_scope(self, *, client_id: str, supplier_id: str) -> None:
        client = self._client_repo.get_by_id(client_id)
        if client is None:
            raise ClientNotFoundError(f"Client not found: {client_id}")
        supplier = self._client_supplier_repo.get_by_id(supplier_id)
        if supplier is None:
            raise ClientSupplierNotFoundError(f"Client supplier not found: {supplier_id}")
        if supplier.client_id != client_id:
            raise ClientSupplierClientMismatchError(
                "Client supplier does not belong to the requested client"
            )


class ListSupplierReferenceImagesUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        reference_repo: SupplierReferenceImageRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._reference_repo = reference_repo

    def execute(self, client_id: str, supplier_id: str) -> Sequence[SupplierReferenceImage]:
        client = self._client_repo.get_by_id(client_id)
        if client is None:
            raise ClientNotFoundError(f"Client not found: {client_id}")
        supplier = self._client_supplier_repo.get_by_id(supplier_id)
        if supplier is None:
            raise ClientSupplierNotFoundError(f"Client supplier not found: {supplier_id}")
        if supplier.client_id != client_id:
            raise ClientSupplierClientMismatchError(
                "Client supplier does not belong to the requested client"
            )
        return self._reference_repo.list_by_supplier(supplier_id)
