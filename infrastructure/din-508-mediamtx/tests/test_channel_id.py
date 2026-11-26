"""Channel identity tests — DIN-508 Phase 2 final corrections."""

from __future__ import annotations

import pytest

from channel_id import (
    MAX_AISLE_CODE_LEN,
    canonical_aisle_code_for_channel,
    channel_slug,
    mediamtx_path,
    normalize_inventory_id,
)

INV_A = "550e8400-e29b-41d4-a716-446655440001"
INV_B = "550e8400-e29b-41d4-a716-446655440002"


def test_uuid_canonical_lowercase() -> None:
    assert normalize_inventory_id("550E8400-E29B-41D4-A716-446655440001") == INV_A


def test_case_insensitive_equivalent_a01() -> None:
    assert channel_slug(INV_A, "A01") == channel_slug(INV_A, "a01")
    assert channel_slug(INV_A, "  A01 ") == channel_slug(INV_A, "a01")


def test_different_codes_different_slugs() -> None:
    assert channel_slug(INV_A, "A01") != channel_slug(INV_A, "A02")


def test_same_code_different_inventories() -> None:
    assert channel_slug(INV_A, "P1") != channel_slug(INV_B, "P1")


def test_special_characters_preserved() -> None:
    assert channel_slug(INV_A, "Pasillo_A_04") == channel_slug(INV_A, "pasillo_a_04")


def test_unicode_upper_eszett_python_collapse() -> None:
    """Python .upper() maps ß → SS; slug may collide with ASCII 'strasse' — SQL probe required for truth."""
    assert canonical_aisle_code_for_channel("straße") == "STRASSE"
    assert channel_slug(INV_A, "straße") == channel_slug(INV_A, "strasse")


def test_accent_may_diverge_from_ascii() -> None:
    assert canonical_aisle_code_for_channel("Café") == "CAFÉ"
    assert channel_slug(INV_A, "Cafe") != channel_slug(INV_A, "Café")


def test_max_length_api_alignment() -> None:
    with pytest.raises(ValueError):
        canonical_aisle_code_for_channel("x" * (MAX_AISLE_CODE_LEN + 1))


def test_empty_raises() -> None:
    with pytest.raises(ValueError):
        canonical_aisle_code_for_channel("   ")


def test_invalid_inventory_uuid() -> None:
    with pytest.raises(ValueError):
        mediamtx_path("not-a-uuid", "A01")
    with pytest.raises(ValueError):
        normalize_inventory_id("550e8400-e29b-41d4-a716-44665544000g")


def test_path_uses_inventory_name_and_aisle() -> None:
    path = mediamtx_path(
        "550E8400-E29B-41D4-A716-446655440001",
        "A-03",
        inventory_name="Prueba18-09",
    )
    assert path == "live/Prueba18-09/A-03"