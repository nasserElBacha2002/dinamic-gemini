"""Channel identity parity with infrastructure/din-508-mediamtx/scripts/channel_id.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.domain.live_stream.channel_identity import (
    channel_slug,
    mediamtx_path,
    normalize_inventory_id,
)

_REPO = Path(__file__).resolve().parents[4]
_SCRIPT = _REPO / "infrastructure" / "din-508-mediamtx" / "scripts" / "channel_id.py"

INV_A = "550e8400-e29b-41d4-a716-446655440001"


def test_matches_infrastructure_script() -> None:
    code = "A-03"
    inv_name = "InventarioA"
    expected = subprocess.check_output(
        [sys.executable, str(_SCRIPT), INV_A, code, inv_name],
        text=True,
    ).strip()
    assert mediamtx_path(INV_A, code, inventory_name=inv_name) == expected


def test_human_path_for_manual_rtmp_entry() -> None:
    assert (
        mediamtx_path(INV_A, "p1", inventory_name="Prueba18-09") == "live/Prueba18-09/P1"
    )
    assert normalize_inventory_id("550E8400-E29B-41D4-A716-446655440001") == INV_A
    assert channel_slug(INV_A, "A01") == channel_slug(INV_A, "a01")


def test_different_inventories_isolated() -> None:
    inv_b = "550e8400-e29b-41d4-a716-446655440002"
    assert channel_slug(INV_A, "P1") != channel_slug(inv_b, "P1")


def test_empty_code_raises() -> None:
    with pytest.raises(ValueError):
        mediamtx_path(INV_A, "   ")