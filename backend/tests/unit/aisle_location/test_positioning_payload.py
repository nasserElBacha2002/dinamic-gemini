"""Unit tests — DINAMIC_POSITION payload + aisle location code normalization."""

from __future__ import annotations

import pytest

from src.domain.aisle_location.entities import normalize_aisle_location_code
from src.domain.aisle_location.payload import (
    build_positioning_label_payload,
    payload_sha256,
    validate_positioning_payload,
)


def test_build_and_validate_dinamic_position_payload() -> None:
    payload = build_positioning_label_payload(
        public_label_id="pl_abc",
        public_position_id="loc-1",
    )
    assert payload["type"] == "DINAMIC_POSITION"
    assert payload["version"] == 1
    assert payload["label_id"] == "pl_abc"
    assert payload["position_id"] == "loc-1"
    validate_positioning_payload(payload)
    assert len(payload_sha256(payload)) == 64


def test_positioning_payload_rejects_item_fields() -> None:
    payload = build_positioning_label_payload(
        public_label_id="pl_abc",
        public_position_id="loc-1",
    )
    payload["sku"] = "X"
    with pytest.raises(ValueError, match="sku"):
        validate_positioning_payload(payload)


def test_normalize_aisle_location_code() -> None:
    assert normalize_aisle_location_code("  a-03  02 ") == "A-03 02"
