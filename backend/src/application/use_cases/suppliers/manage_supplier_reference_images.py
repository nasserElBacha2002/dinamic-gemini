"""Supplier reference image read/delete — Phase C1 foundation + Phase C2 API."""

from __future__ import annotations

import logging

from src.application.errors import (
    ClientNotFoundError,
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
    SupplierReferenceImageNotFoundError,
)
from src.application.ports.repositories import (
    ClientRepository,
    ClientSupplierRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.services import ArtifactStorage
from src.domain.client_supplier.reference_image import SupplierReferenceImage

logger = logging.getLogger(__name__)


class GetSupplierReferenceImageUseCase:
    """Return one supplier reference image after enforcing client/supplier/image ownership."""

    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        reference_repo: SupplierReferenceImageRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._reference_repo = reference_repo

    def execute(self, client_id: str, supplier_id: str, image_id: str) -> SupplierReferenceImage:
        self._validate_supplier_in_client_scope(client_id=client_id, supplier_id=supplier_id)
        image = self._reference_repo.get_by_id(image_id)
        if image is None or image.client_supplier_id != supplier_id:
            raise SupplierReferenceImageNotFoundError(
                f"Supplier reference image not found in supplier scope: {image_id}"
            )
        return image

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


class DeleteSupplierReferenceImageUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        reference_repo: SupplierReferenceImageRepository,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._reference_repo = reference_repo
        self._artifact_storage = artifact_storage

    def execute(self, client_id: str, supplier_id: str, image_id: str) -> None:
        self._validate_supplier_in_client_scope(client_id=client_id, supplier_id=supplier_id)

        image = self._reference_repo.get_by_id(image_id)
        if image is None or image.client_supplier_id != supplier_id:
            raise SupplierReferenceImageNotFoundError(
                f"Supplier reference image not found in supplier scope: {image_id}"
            )

        self._reference_repo.delete(image_id)
        key_to_delete = (image.storage_key or image.storage_path or "").strip()
        if key_to_delete:
            try:
                self._artifact_storage.delete_file(key_to_delete)
            except Exception as cleanup_error:
                logger.warning(
                    "Delete cleanup failed for supplier reference image file %s: %s",
                    key_to_delete,
                    cleanup_error,
                )

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
