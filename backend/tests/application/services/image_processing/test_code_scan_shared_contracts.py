"""Contract tests: shared fixtures vs EncodedLabelPayloadParser (authority).

Fixtures live in contracts/code-scan/v1/ and are also executed by the mobile
TypeScript parser. Do not generate fixtures from either implementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.services.image_processing.encoded_label_payload_parser import (
    EncodedLabelPayloadParser,
)

ROOT = Path(__file__).resolve().parents[5]
CONTRACTS = ROOT / "contracts" / "code-scan" / "v1"


def _load(name: str) -> list[dict]:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _quantity_status(parsed) -> str:
    if parsed.quantity is not None:
        return "PRESENT"
    if any(
        w in parsed.warnings
        for w in (
            "QUANTITY_NOT_POSITIVE",
            "QUANTITY_ABOVE_MAX",
            "QUANTITY_NOT_INTEGER",
            "QUANTITY_DECIMAL_NOT_ALLOWED",
        )
    ):
        return "INVALID"
    return "MISSING"


def _status(parsed) -> str:
    return "VALID" if parsed.has_valid_code else "INVALID"


def _format_version(parsed) -> str:
    if parsed.format.value == "DI1":
        return "DI1"
    # Mobile contract uses "v1" for non-DI1; Python stores None.
    return parsed.version or "v1"


def _error_code(parsed) -> str | None:
    if parsed.has_valid_code:
        return None
    for code in (
        "EMPTY_OR_UNPARSEABLE_PAYLOAD",
        "NO_INTERNAL_CODE",
        "CODE_LENGTH_OUT_OF_RANGE",
        "CODE_CONTROL_CHARACTERS",
    ):
        if code in parsed.warnings:
            return code
    return "NO_INTERNAL_CODE"


@pytest.mark.parametrize("fixture", _load("valid.json"), ids=lambda f: f["name"])
def test_valid_fixtures(fixture: dict) -> None:
    quantity_max = int(fixture.get("quantityMax") or 99_999_999)
    parser = EncodedLabelPayloadParser(quantity_max=quantity_max)
    parsed = parser.parse(fixture["raw"])
    expected = fixture["expected"]
    assert _status(parsed) == expected["status"]
    assert parsed.format.value == expected["format"]
    assert parsed.internal_code == expected["internalCode"]
    assert parsed.quantity == expected["quantity"]
    assert _quantity_status(parsed) == expected["quantityStatus"]
    assert _format_version(parsed) == expected["formatVersion"]
    assert sorted(parsed.warnings) == sorted(expected.get("warnings") or [])


@pytest.mark.parametrize("fixture", _load("invalid.json"), ids=lambda f: f["name"])
def test_invalid_fixtures(fixture: dict) -> None:
    quantity_max = int(fixture.get("quantityMax") or 99_999_999)
    parser = EncodedLabelPayloadParser(quantity_max=quantity_max)
    parsed = parser.parse(fixture["raw"])
    expected = fixture["expected"]
    assert _status(parsed) == expected["status"]
    assert parsed.format.value == expected["format"]
    assert parsed.internal_code == expected["internalCode"]
    assert parsed.quantity == expected["quantity"]
    assert _quantity_status(parsed) == expected["quantityStatus"]
    assert _format_version(parsed) == expected["formatVersion"]
    if expected.get("errorCode"):
        assert _error_code(parsed) == expected["errorCode"]
    assert sorted(parsed.warnings) == sorted(expected.get("warnings") or [])
