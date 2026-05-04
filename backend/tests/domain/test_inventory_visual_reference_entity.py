"""
Unit tests for InventoryVisualReference domain entity — v3.2.4.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.inventory.visual_reference import InventoryVisualReference


def _now() -> datetime:
    return datetime(2025, 3, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_valid_construction() -> None:
    ref = InventoryVisualReference(
        id="ref-1",
        inventory_id="inv-1",
        filename="label.png",
        storage_path="inventories/inv-1/visual_references/ref-1.png",
        mime_type="image/png",
        file_size=123,
        created_at=_now(),
    )
    assert ref.id == "ref-1"
    assert ref.file_size == 123


@pytest.mark.parametrize(
    "field_name", ["id", "inventory_id", "filename", "storage_path", "mime_type"]
)
def test_empty_string_fields_rejected(field_name: str) -> None:
    kwargs = dict(
        id="ref-1",
        inventory_id="inv-1",
        filename="f.png",
        storage_path="inventories/inv-1/visual_references/ref-1.png",
        mime_type="image/png",
        file_size=1,
        created_at=_now(),
    )
    kwargs[field_name] = ""  # type: ignore[assignment]
    with pytest.raises(ValueError):
        InventoryVisualReference(**kwargs)  # type: ignore[arg-type]


def test_negative_file_size_rejected() -> None:
    with pytest.raises(ValueError):
        InventoryVisualReference(
            id="ref-1",
            inventory_id="inv-1",
            filename="label.png",
            storage_path="inventories/inv-1/visual_references/ref-1.png",
            mime_type="image/png",
            file_size=-1,
            created_at=_now(),
        )


def test_missing_created_at_rejected() -> None:
    with pytest.raises(ValueError):
        InventoryVisualReference(
            id="ref-1",
            inventory_id="inv-1",
            filename="label.png",
            storage_path="inventories/inv-1/visual_references/ref-1.png",
            mime_type="image/png",
            file_size=1,
            created_at=None,  # type: ignore[arg-type]
        )
