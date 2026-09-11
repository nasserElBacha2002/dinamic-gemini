"""TXT supplier-profile path (generic SIMPLE/SEGMENTED — no hardcoded prefixes)."""

from __future__ import annotations

from src.application.services.dinamic_scanner_txt_parser import parse_dinamic_scanner_txt
from src.domain.client_supplier.extraction_profile import (
    CharacterSetPolicy,
    minimal_supplier_item_configuration,
    minimal_supplier_position_configuration,
)


def test_txt_supplier_simple_item_and_position() -> None:
    item = minimal_supplier_item_configuration(
        expected_prefix="PRD",
        exact_length=10,
        character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
    )
    position = minimal_supplier_position_configuration(
        expected_prefix="LOC",
        exact_length=10,
        character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
    )
    body = b"LOC-A01-02\nPRD-123456\n"
    parsed = parse_dinamic_scanner_txt(
        body,
        item_configuration=item,
        position_configuration=position,
    )
    assert len(parsed.positions) == 1
    assert parsed.positions[0].label_id == "LOC-A01-02"
    assert len(parsed.products) == 1
    assert parsed.products[0].label_id == "PRD-123456"
    assert parsed.products[0].quantity is None
    assert not parsed.products[0].errors


def test_txt_without_profiles_keeps_unknown_record() -> None:
    parsed = parse_dinamic_scanner_txt(b"LOC-A01-02\nPRD-123456\n")
    assert parsed.positions == ()
    assert parsed.products == ()
    assert any("unknown_record" in w for w in parsed.parse_warnings)
