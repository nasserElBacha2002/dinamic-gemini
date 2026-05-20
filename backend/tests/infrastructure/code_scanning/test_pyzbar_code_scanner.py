"""Tests for PyzbarCodeScanner — mapping fakes and optional fixture integration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.code_scans.entities import CodeScanDetectionStatus, CodeType
from src.infrastructure.code_scanning.pyzbar_code_scanner import (
    PyzbarCodeScanner,
    PyzbarUnavailableError,
    _symbol_bounding_box,
)
from src.infrastructure.code_scanning.pyzbar_type_mapping import map_pyzbar_type_name

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "code_scans"


def _asset(asset_id: str = "a1") -> SourceAsset:
    from datetime import datetime, timezone

    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    return SourceAsset(
        id=asset_id,
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="test.jpg",
        storage_path="uploads/test.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )


def test_symbol_bounding_box_rect_polygon_contract() -> None:
    sym = SimpleNamespace(
        rect=SimpleNamespace(left=10, top=20, width=30, height=40),
        polygon=[
            SimpleNamespace(x=10, y=20),
            SimpleNamespace(x=40, y=20),
            SimpleNamespace(x=40, y=60),
            SimpleNamespace(x=10, y=60),
        ],
    )
    bbox = _symbol_bounding_box(sym)
    assert bbox is not None
    assert bbox["format"] == "rect_polygon"
    assert bbox["rect"]["x"] == 10.0
    assert bbox["polygon"][0] == [10.0, 20.0]


@patch("src.infrastructure.code_scanning.pyzbar_code_scanner._import_pyzbar")
@patch("src.infrastructure.code_scanning.pyzbar_code_scanner.decode_bytes_to_rgb_image")
def test_scan_asset_maps_pyzbar_symbols(mock_decode: MagicMock, mock_import: MagicMock) -> None:
    mock_decode.return_value = MagicMock()
    fake_symbol = SimpleNamespace(
        data=b"SKU-99",
        type=SimpleNamespace(name="EAN13"),
        rect=SimpleNamespace(left=0, top=0, width=10, height=10),
        polygon=[],
        quality=80,
    )
    mock_import.return_value = MagicMock(return_value=[fake_symbol])
    scanner = PyzbarCodeScanner()
    results = scanner.scan_asset(_asset(), content=b"fake-image")
    assert len(results) == 1
    assert results[0].code_type == CodeType.BARCODE
    assert results[0].code_value == "SKU-99"
    assert results[0].detection_status == CodeScanDetectionStatus.DETECTED
    assert results[0].bounding_box_json is not None
    assert map_pyzbar_type_name("EAN13") == CodeType.BARCODE


@patch("src.infrastructure.code_scanning.pyzbar_code_scanner._import_pyzbar")
def test_scan_asset_requires_content(mock_import: MagicMock) -> None:
    mock_import.return_value = MagicMock()
    scanner = PyzbarCodeScanner()
    with pytest.raises(ValueError, match="requires image bytes"):
        scanner.scan_asset(_asset(), content=None)


@pytest.mark.skipif(
    not (FIXTURES / "qr_simple.png").is_file(),
    reason="fixture qr_simple.png not generated",
)
def test_integration_detects_qr_from_fixture() -> None:
    try:
        scanner = PyzbarCodeScanner()
    except PyzbarUnavailableError:
        pytest.skip("pyzbar/libzbar not available")
    content = (FIXTURES / "qr_simple.png").read_bytes()
    results = scanner.scan_asset(_asset(), content=content)
    assert any(r.code_type == CodeType.QR for r in results)
    assert any("PHASE2" in (r.code_value or "") for r in results)


@pytest.mark.skipif(
    not (FIXTURES / "qr_simple.png").is_file(),
    reason="fixture qr_simple.png not generated",
)
def test_integration_empty_png_no_detections() -> None:
    import io

    from PIL import Image

    try:
        scanner = PyzbarCodeScanner()
    except PyzbarUnavailableError:
        pytest.skip("pyzbar/libzbar not available")
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color="white").save(buf, format="PNG")
    content = buf.getvalue()
    results = scanner.scan_asset(_asset(), content=content)
    assert results == []
