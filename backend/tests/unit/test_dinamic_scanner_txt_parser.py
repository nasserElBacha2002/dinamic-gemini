from __future__ import annotations

import pytest

from src.application.services.dinamic_scanner_txt_parser import (
    aisle_code_from_txt_filename,
    parse_dinamic_scanner_txt,
)
from src.domain.dinamic_scanner_txt.errors import (
    TXT_EMPTY,
    DinamicScannerTxtImportError,
)


def _txt(*lines: str) -> bytes:
    return "\n".join(lines).encode()


def test_parser_single_product_with_position() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            "D1|LABEL00001|SKU001|100|A",
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
            "D1|LABEL00001|SKU001|100|A",
            "D1|LABEL00002|SKU002|50|B",
        )
    )

    assert all(product.position is parsed.positions[0] for product in parsed.products)


def test_parser_position_change() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            "D1|LABEL00001|SKU001|100|A",
            "POSITION|POS002|05|LEFT",
            "D1|LABEL00002|SKU002|50|B",
        )
    )

    assert parsed.products[0].position is parsed.positions[0]
    assert parsed.products[1].position is parsed.positions[1]


def test_parser_invalid_position_resets_active_context() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            "D1|LABEL1|SKU1|10|A",
            "POSITION|MALFORMADA",
            "D1|LABEL2|SKU2|20|B",
            "POSITION|POS002|05|LEFT",
            "D1|LABEL3|SKU3|30|C",
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
    parsed = parse_dinamic_scanner_txt(_txt("D1|LABEL00001|SKU001|100|A"))
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
