"""Tests for :mod:`src.application.services.inventory_visual_reference_lookup`."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.inventory_visual_reference_lookup import (
    select_visual_reference_by_id,
)
from src.domain.inventory.visual_reference import InventoryVisualReference

_now = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ref(rid: str) -> InventoryVisualReference:
    return InventoryVisualReference(
        id=rid,
        inventory_id="inv",
        filename="f.jpg",
        storage_path="p",
        mime_type="image/jpeg",
        file_size=1,
        created_at=_now,
    )


def test_select_visual_reference_by_id() -> None:
    a, b = _ref("r1"), _ref("r2")
    assert select_visual_reference_by_id([a, b], "r2") is b
    assert select_visual_reference_by_id([a, b], "rx") is None
