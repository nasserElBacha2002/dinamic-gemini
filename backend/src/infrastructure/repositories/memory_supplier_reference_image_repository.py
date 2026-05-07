"""In-memory implementation of SupplierReferenceImageRepository — Phase C1."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import SupplierReferenceImageRepository
from src.domain.client_supplier.reference_image import SupplierReferenceImage


class MemorySupplierReferenceImageRepository(SupplierReferenceImageRepository):
    def __init__(self) -> None:
        self._store: dict[str, SupplierReferenceImage] = {}

    def get_by_id(self, reference_image_id: str) -> SupplierReferenceImage | None:
        return self._store.get(reference_image_id)

    def create(self, reference_image: SupplierReferenceImage) -> None:
        if reference_image.id in self._store:
            raise ValueError(
                f"SupplierReferenceImage with id={reference_image.id!r} already exists"
            )
        self._store[reference_image.id] = reference_image

    def create_many(self, reference_images: Sequence[SupplierReferenceImage]) -> None:
        for image in reference_images:
            if image.id in self._store:
                raise ValueError(
                    f"SupplierReferenceImage with id={image.id!r} already exists"
                )
        for image in reference_images:
            self._store[image.id] = image

    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierReferenceImage]:
        rows = [
            image
            for image in self._store.values()
            if image.client_supplier_id == client_supplier_id
        ]
        rows.sort(key=lambda image: (image.created_at, image.id))
        return rows

    def delete(self, reference_image_id: str) -> None:
        self._store.pop(reference_image_id, None)
