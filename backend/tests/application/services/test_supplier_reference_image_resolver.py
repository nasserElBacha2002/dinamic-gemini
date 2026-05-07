"""Tests for SupplierReferenceImageResolver — Phase C7."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import SupplierReferenceImageRepository
from src.application.services.supplier_reference_image_resolver import (
    ROLE_SUPPLIER_REFERENCE,
    SupplierReferenceImageResolver,
)
from src.domain.client_supplier.reference_image import SupplierReferenceImage


class _MemSupplierRepo(SupplierReferenceImageRepository):
    def __init__(self, rows: Sequence[SupplierReferenceImage]) -> None:
        self._rows = list(rows)

    def get_by_id(self, reference_image_id: str) -> SupplierReferenceImage | None:
        return next((r for r in self._rows if r.id == reference_image_id), None)

    def create(self, reference_image: SupplierReferenceImage) -> None:
        self._rows.append(reference_image)

    def create_many(self, reference_images: Sequence[SupplierReferenceImage]) -> None:
        self._rows.extend(reference_images)

    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierReferenceImage]:
        out = [r for r in self._rows if r.client_supplier_id == client_supplier_id]
        out.sort(key=lambda r: (r.created_at, r.id))
        return out

    def delete(self, reference_image_id: str) -> None:
        self._rows = [r for r in self._rows if r.id != reference_image_id]


def _img(supplier_id: str, rid: str, *, created: datetime | None = None) -> SupplierReferenceImage:
    now = created or datetime(2025, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    return SupplierReferenceImage(
        id=rid,
        client_supplier_id=supplier_id,
        filename=f"{rid}.jpg",
        storage_path=f"suppliers/{supplier_id}/{rid}.jpg",
        mime_type="image/jpeg",
        file_size=1,
        created_at=now,
        updated_at=now,
    )


def test_resolver_maps_rows_to_visual_reference_context() -> None:
    repo = _MemSupplierRepo([_img("sup-1", "r1")])
    resolver = SupplierReferenceImageResolver(repo)
    out = resolver.resolve_for_supplier("sup-1")
    assert len(out) == 1
    assert out[0].reference_id == "r1"
    assert out[0].source_path == "suppliers/sup-1/r1.jpg"
    assert out[0].mime_type == "image/jpeg"
    assert out[0].role == ROLE_SUPPLIER_REFERENCE
    assert out[0].created_at is not None


def test_resolver_returns_empty_when_supplier_has_no_images() -> None:
    resolver = SupplierReferenceImageResolver(_MemSupplierRepo([]))
    assert resolver.resolve_for_supplier("sup-x") == []


def test_resolver_returns_empty_for_blank_supplier_id() -> None:
    resolver = SupplierReferenceImageResolver(_MemSupplierRepo([_img("sup-1", "r1")]))
    assert resolver.resolve_for_supplier("") == []
    assert resolver.resolve_for_supplier("   ") == []
    assert resolver.resolve_for_supplier(None) == []
