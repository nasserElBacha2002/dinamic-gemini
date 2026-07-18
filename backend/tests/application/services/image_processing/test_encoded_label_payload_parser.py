"""Unit tests for the Phase 3 encoded label payload parser."""

from __future__ import annotations

from src.application.services.image_processing.encoded_label_payload_parser import (
    EncodedLabelPayloadParser,
    LabelPayloadFormat,
)


def _parser(quantity_max: int = 99999999) -> EncodedLabelPayloadParser:
    return EncodedLabelPayloadParser(quantity_max=quantity_max)


def test_pipe_payload_resolves_code_and_quantity() -> None:
    parsed = _parser().parse("ABC123|5")
    assert parsed.format is LabelPayloadFormat.PIPE
    assert parsed.internal_code == "ABC123"
    assert parsed.quantity == 5
    assert parsed.warnings == ()


def test_di1_legacy_payload_decodes_urlencoded_code() -> None:
    parsed = _parser().parse("DI1|C=ABC%20123|Q=3")
    assert parsed.format is LabelPayloadFormat.DI1
    assert parsed.version == "DI1"
    assert parsed.internal_code == "ABC 123"
    assert parsed.quantity == 3


def test_plain_code_has_no_quantity() -> None:
    parsed = _parser().parse("PLAINCODE")
    assert parsed.format is LabelPayloadFormat.PLAIN
    assert parsed.internal_code == "PLAINCODE"
    assert parsed.quantity is None
    assert "QUANTITY_MISSING" in parsed.warnings


def test_leading_zeros_preserved_in_code() -> None:
    parsed = _parser().parse("007123|9")
    assert parsed.internal_code == "007123"
    assert parsed.internal_code.startswith("007")
    assert parsed.quantity == 9


def test_quantity_above_max_flags_but_keeps_code() -> None:
    parsed = _parser(quantity_max=10).parse("ABC|99")
    assert parsed.internal_code == "ABC"
    assert parsed.quantity is None
    assert "QUANTITY_ABOVE_MAX" in parsed.warnings


def test_empty_payload_is_unknown() -> None:
    parsed = _parser().parse("")
    assert parsed.format is LabelPayloadFormat.UNKNOWN
    assert parsed.internal_code is None
    assert parsed.quantity is None
    assert "EMPTY_OR_UNPARSEABLE_PAYLOAD" in parsed.warnings


def test_control_characters_in_code_rejected() -> None:
    parsed = _parser().parse("AB\x01C|2")
    # Pipe regex excludes only '|' and newline, so control char reaches validation.
    assert parsed.internal_code is None
    assert "CODE_CONTROL_CHARACTERS" in parsed.warnings
