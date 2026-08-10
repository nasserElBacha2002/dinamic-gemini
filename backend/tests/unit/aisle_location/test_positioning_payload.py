"""Unit tests — DINAMIC_POSITION payload + aisle location code normalization."""

from __future__ import annotations

import pytest

from src.domain.aisle_location.entities import normalize_aisle_location_code
from src.domain.aisle_location.label_entities import (
    POSITIONING_LABEL_PAYLOAD_VERSION,
    POSITIONING_LABEL_PAYLOAD_VERSION_V2,
)
from src.domain.aisle_location.payload import (
    build_positioning_label_payload,
    canonicalize_positioning_payload_for_signing,
    payload_sha256,
    validate_positioning_payload,
)
from src.domain.client_position_label.hierarchy import PositionSide


def test_build_and_validate_dinamic_position_payload() -> None:
    payload = build_positioning_label_payload(
        public_label_id="pl_abc",
        public_position_id="loc-1",
    )
    assert payload["type"] == "DINAMIC_POSITION"
    assert payload["version"] == POSITIONING_LABEL_PAYLOAD_VERSION
    assert payload["label_id"] == "pl_abc"
    assert payload["position_id"] == "loc-1"
    validate_positioning_payload(payload)
    assert len(payload_sha256(payload)) == 64
    assert "pallet" not in payload


def test_build_and_validate_positioning_payload_v2_hierarchy() -> None:
    payload = build_positioning_label_payload(
        public_label_id="pl_v2",
        pallet="P12",
        side=PositionSide.LEFT,
        level=3,
        marker_index=1,
        marker_total=3,
    )
    assert payload["version"] == POSITIONING_LABEL_PAYLOAD_VERSION_V2
    assert payload["pallet"] == "P12"
    assert payload["side"] == "LEFT"
    assert payload["level"] == 3
    assert payload["marker_index"] == 1
    assert payload["marker_total"] == 3
    validate_positioning_payload(payload)
    # HMAC signing still excludes only signature (hierarchy fields remain).
    signed = dict(payload)
    signed["signature"] = "deadbeef"
    signed["key_version"] = 1
    canon = canonicalize_positioning_payload_for_signing(signed)
    assert "signature" not in canon
    assert "pallet" in canon
    assert "marker_index" in canon


def test_validate_v2_requires_hierarchy() -> None:
    payload = {
        "type": "DINAMIC_POSITION",
        "version": 2,
        "label_id": "pl_x",
    }
    with pytest.raises(ValueError, match="hierarchy"):
        validate_positioning_payload(payload)


def test_validate_v2_rejects_bad_side() -> None:
    payload = build_positioning_label_payload(
        public_label_id="pl_v2",
        pallet="P1",
        side="LEFT",
        level=1,
        marker_index=1,
        marker_total=1,
    )
    payload["side"] = "CENTER"
    with pytest.raises(ValueError, match="side"):
        validate_positioning_payload(payload)


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
