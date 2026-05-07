from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.client_supplier.reference_image import SupplierReferenceImage


def _now() -> datetime:
    return datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)


def test_supplier_reference_image_valid_entity() -> None:
    now = _now()
    image = SupplierReferenceImage(
        id="img-1",
        client_supplier_id="sup-1",
        filename="front.png",
        storage_path="client_suppliers/sup-1/reference_images/img-1.png",
        mime_type="image/png",
        file_size=1024,
        created_at=now,
        updated_at=now,
    )
    assert image.id == "img-1"
    assert image.client_supplier_id == "sup-1"


@pytest.mark.parametrize(
    ("field", "payload"),
    [
        ("id", {"id": ""}),
        ("client_supplier_id", {"client_supplier_id": ""}),
        ("filename", {"filename": ""}),
        ("storage_path", {"storage_path": ""}),
        ("mime_type", {"mime_type": ""}),
    ],
)
def test_supplier_reference_image_required_string_fields(
    field: str, payload: dict[str, str]
) -> None:
    now = _now()
    kwargs = {
        "id": "img-1",
        "client_supplier_id": "sup-1",
        "filename": "f.jpg",
        "storage_path": "client_suppliers/sup-1/reference_images/img-1.jpg",
        "mime_type": "image/jpeg",
        "file_size": 1,
        "created_at": now,
        "updated_at": now,
    }
    kwargs.update(payload)
    with pytest.raises(ValueError, match=field):
        SupplierReferenceImage(**kwargs)


def test_supplier_reference_image_file_size_must_be_non_negative() -> None:
    now = _now()
    with pytest.raises(ValueError, match="file_size"):
        SupplierReferenceImage(
            id="img-1",
            client_supplier_id="sup-1",
            filename="front.png",
            storage_path="client_suppliers/sup-1/reference_images/img-1.png",
            mime_type="image/png",
            file_size=-1,
            created_at=now,
            updated_at=now,
        )
