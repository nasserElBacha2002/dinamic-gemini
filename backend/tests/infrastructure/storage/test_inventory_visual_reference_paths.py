"""
Unit tests for inventory visual reference storage path convention — v3.2.4.
"""

from __future__ import annotations

from src.application.utils.inventory_visual_reference_paths import (
    DEFAULT_EXT,
    extension_from_mime_type,
    visual_reference_storage_path,
)


def test_extension_from_mime_type_jpeg() -> None:
    assert extension_from_mime_type("image/jpeg") == "jpg"
    assert extension_from_mime_type("image/jpg") == "jpg"


def test_extension_from_mime_type_png_webp() -> None:
    assert extension_from_mime_type("image/png") == "png"
    assert extension_from_mime_type("image/webp") == "webp"


def test_extension_from_mime_type_unknown_defaults_to_bin() -> None:
    assert extension_from_mime_type("image/unknown") == DEFAULT_EXT
    assert extension_from_mime_type("") == DEFAULT_EXT
    assert extension_from_mime_type("application/octet-stream") == DEFAULT_EXT


def test_extension_from_mime_type_strips_and_lowercase() -> None:
    assert extension_from_mime_type("  IMAGE/PNG  ") == "png"
    assert extension_from_mime_type("image/jpeg; charset=utf-8") == "jpg"


def test_visual_reference_storage_path_format() -> None:
    path = visual_reference_storage_path(
        inventory_id="inv-123",
        reference_id="ref-456",
        mime_type="image/png",
    )
    assert path == "inventories/inv-123/visual_references/ref-456.png"


def test_visual_reference_storage_path_does_not_use_original_filename() -> None:
    """Path must be deterministic from inventory_id, reference_id, mime_type only."""
    path = visual_reference_storage_path(
        inventory_id="inv-a",
        reference_id="ref-b",
        mime_type="image/jpeg",
    )
    assert "visual_references" in path
    assert path.endswith("ref-b.jpg")
    assert path.startswith("inventories/inv-a/")


def test_visual_reference_storage_path_deterministic() -> None:
    p1 = visual_reference_storage_path("i1", "r1", "image/webp")
    p2 = visual_reference_storage_path("i1", "r1", "image/webp")
    assert p1 == p2
