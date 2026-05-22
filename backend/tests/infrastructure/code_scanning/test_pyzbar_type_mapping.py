"""Unit tests for pyzbar type mapping (no libzbar required)."""

from __future__ import annotations

from src.domain.code_scans.entities import CodeType
from src.infrastructure.code_scanning.pyzbar_type_mapping import (
    decode_symbol_bytes,
    map_pyzbar_type_name,
)


def test_qr_type_maps_to_qr() -> None:
    assert map_pyzbar_type_name("QRCODE") == CodeType.QR
    assert map_pyzbar_type_name("QR_CODE") == CodeType.QR


def test_barcode_types_map_to_barcode() -> None:
    assert map_pyzbar_type_name("EAN13") == CodeType.BARCODE
    assert map_pyzbar_type_name("CODE128") == CodeType.BARCODE


def test_datamatrix_maps() -> None:
    assert map_pyzbar_type_name("DATAMATRIX") == CodeType.DATAMATRIX


def test_unknown_type() -> None:
    assert map_pyzbar_type_name("WEIRD") == CodeType.UNKNOWN


def test_decode_symbol_bytes_utf8_and_latin1() -> None:
    assert decode_symbol_bytes(b"hello") == "hello"
    assert decode_symbol_bytes(b"\xff\xfe") == "\xff\xfe"
