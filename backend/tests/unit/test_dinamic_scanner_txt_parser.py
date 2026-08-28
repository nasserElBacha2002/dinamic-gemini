from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.services.dinamic_scanner_txt_parser import (
    aisle_code_from_txt_filename,
    parse_dinamic_scanner_txt,
)
from src.domain.dinamic_scanner_txt.errors import (
    TXT_EMPTY,
    DinamicScannerTxtImportError,
)
from src.domain.product_labels.format import build_product_label_payload

_VECTORS = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "product-labels"
    / "v1"
    / "checksum-vectors.json"
)


def _load_vectors() -> dict:
    return json.loads(_VECTORS.read_text(encoding="utf-8"))


def _valid_d1_line(label_id: str = "A1B2C3D4E5", sku: str = "SKU001", qty: int = 100) -> str:
    return build_product_label_payload(label_id=label_id, internal_code=sku, quantity=qty)


def _txt(*lines: str) -> bytes:
    return "\n".join(lines).encode()


def test_parser_single_product_with_position() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            _valid_d1_line(),
        )
    )

    assert len(parsed.positions) == 1
    assert parsed.positions[0].label_id == "POS001"
    assert parsed.positions[0].side == "RIGHT"
    assert parsed.products[0].position is parsed.positions[0]
    assert parsed.products[0].errors == ()


def test_parser_multiple_products_same_position() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU001", qty=100),
            _valid_d1_line(label_id="FGHJKMNPQR", sku="SKU002", qty=50),
        )
    )

    assert all(product.position is parsed.positions[0] for product in parsed.products)


def test_parser_position_change() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU001", qty=100),
            "POSITION|POS002|05|LEFT",
            _valid_d1_line(label_id="FGHJKMNPQR", sku="SKU002", qty=50),
        )
    )

    assert parsed.products[0].position is parsed.positions[0]
    assert parsed.products[1].position is parsed.positions[1]


def test_parser_invalid_position_resets_active_context() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU1", qty=10),
            "POSITION|MALFORMADA",
            _valid_d1_line(label_id="FGHJKMNPQR", sku="SKU2", qty=20),
            "POSITION|POS002|05|LEFT",
            _valid_d1_line(label_id="STVWXYZ234", sku="SKU3", qty=30),
        )
    )

    assert parsed.products[0].position.label_id == "POS001"
    assert parsed.products[1].position is None
    assert "product:no_valid_active_position" in parsed.products[1].errors
    assert parsed.products[2].position.label_id == "POS002"


def test_parser_rejects_invalid_side() -> None:
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS1|04|CENTER"))
    assert parsed.positions == ()
    assert any("side:invalid" in warning for warning in parsed.parse_warnings)


def test_parser_product_before_position_is_rejected() -> None:
    parsed = parse_dinamic_scanner_txt(_txt(_valid_d1_line()))
    assert "product:no_valid_active_position" in parsed.products[0].errors


def test_parser_invalid_line_is_warning() -> None:
    parsed = parse_dinamic_scanner_txt(_txt("INVALID"))
    assert parsed.products == ()
    assert any("unknown_record" in warning for warning in parsed.parse_warnings)


def test_parser_empty_file_raises() -> None:
    with pytest.raises(DinamicScannerTxtImportError) as exc:
        parse_dinamic_scanner_txt(b"   \n  ")
    assert exc.value.code == TXT_EMPTY


def test_aisle_code_from_filename_strips_extension() -> None:
    assert aisle_code_from_txt_filename("Pasillo_A_04.txt") == "Pasillo_A_04"


def test_aisle_code_rejects_path_traversal() -> None:
    with pytest.raises(DinamicScannerTxtImportError):
        aisle_code_from_txt_filename("../secret.txt")


def test_txt_valid_d1_accepted() -> None:
    line = _valid_d1_line()
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", line))
    assert parsed.products[0].errors == ()


def test_txt_checksum_invalid_rejected() -> None:
    vectors = _load_vectors()
    bad = next(
        v["tampered_payload"]
        for v in vectors["vectors"]
        if v["name"] == "checksum-fail-tampered-qty"
    )
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", bad))
    assert "d1:checksum_failed" in parsed.products[0].errors


def test_txt_malformed_d1_rejected() -> None:
    vectors = _load_vectors()
    raw = next(
        v["raw"]
        for v in vectors["vectors"]
        if v["name"] == "malformed-grammar-bad-label"
    )
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", raw))
    assert "d1:malformed" in parsed.products[0].errors


def test_txt_d2_rejected() -> None:
    vectors = _load_vectors()
    raw = next(v["raw"] for v in vectors["vectors"] if v["name"] == "unknown-version-d2")
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", raw))
    assert "d1:unknown_version" in parsed.products[0].errors
