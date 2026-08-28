"""TXT parser boundary tests — exact limit-1 / limit / limit+1."""

from __future__ import annotations

import pytest

from src.application.services.dinamic_scanner_txt_parser import parse_dinamic_scanner_txt
from src.domain.dinamic_scanner_txt.errors import (
    TXT_LINE_TOO_LONG,
    TXT_TOO_MANY_LINES,
    DinamicScannerTxtImportError,
)
from src.domain.product_labels.format import build_product_label_payload


def _position_line(label: str = "POS", pallet: str = "01", side: str = "LEFT") -> str:
    return f"POSITION|{label}|{pallet}|{side}"


def _position_line_exact_length(total: int) -> str:
    prefix = "POSITION|"
    suffix = "|01|LEFT"
    mid_len = total - len(prefix) - len(suffix)
    if mid_len < 1:
        raise ValueError("total too small for POSITION record")
    return f"{prefix}{'X' * mid_len}{suffix}"


def _d1_line(*, sku: str = "SKU", qty: int = 1) -> str:
    return build_product_label_payload(label_id="A1B2C3D4E5", internal_code=sku, quantity=qty)


def test_max_lines_limit_minus_one_succeeds() -> None:
    limit = 5
    lines = [_position_line(f"P{i}") for i in range(limit - 1)]
    lines.append(_d1_line())
    content = "\n".join(lines).encode()
    parsed = parse_dinamic_scanner_txt(content, max_lines=limit, max_line_length=512)
    assert len(parsed.positions) == limit - 1


def test_max_lines_at_limit_succeeds() -> None:
    limit = 5
    lines = [_position_line(f"P{i}") for i in range(limit)]
    content = "\n".join(lines).encode()
    parsed = parse_dinamic_scanner_txt(content, max_lines=limit, max_line_length=512)
    assert len(parsed.positions) == limit


def test_max_lines_limit_plus_one_raises() -> None:
    limit = 5
    lines = [_position_line(f"P{i}") for i in range(limit + 1)]
    content = "\n".join(lines).encode()
    with pytest.raises(DinamicScannerTxtImportError) as exc:
        parse_dinamic_scanner_txt(content, max_lines=limit, max_line_length=512)
    assert exc.value.code == TXT_TOO_MANY_LINES


def test_max_line_length_limit_minus_one_succeeds() -> None:
    limit = 40
    line = _position_line_exact_length(limit - 1)
    assert len(line) == limit - 1
    content = f"{line}\n{_d1_line()}".encode()
    parsed = parse_dinamic_scanner_txt(content, max_lines=10, max_line_length=limit)
    assert len(parsed.positions) == 1


def test_max_line_length_at_limit_succeeds() -> None:
    limit = 40
    line = _position_line_exact_length(limit)
    assert len(line) == limit
    content = f"{line}\n{_d1_line()}".encode()
    parsed = parse_dinamic_scanner_txt(content, max_lines=10, max_line_length=limit)
    assert len(parsed.positions) == 1


def test_max_line_length_limit_plus_one_raises() -> None:
    limit = 40
    line = _position_line_exact_length(limit + 1)
    assert len(line) == limit + 1
    content = f"{line}\n{_d1_line()}".encode()
    with pytest.raises(DinamicScannerTxtImportError) as exc:
        parse_dinamic_scanner_txt(content, max_lines=10, max_line_length=limit)
    assert exc.value.code == TXT_LINE_TOO_LONG
