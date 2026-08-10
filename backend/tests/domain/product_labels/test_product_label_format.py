"""Golden vectors + parser tests for D1 product labels."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domain.product_labels.format import (
    ProductLabelValidationStatus,
    build_product_label_payload,
    compute_product_label_checksum,
    parse_product_label_payload,
)

_VECTORS = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "product-labels"
    / "v1"
    / "checksum-vectors.json"
)


def _load_vectors() -> dict:
    return json.loads(_VECTORS.read_text(encoding="utf-8"))


def test_checksum_vectors_match_contract() -> None:
    data = _load_vectors()
    for vec in data["vectors"]:
        if "checksum" not in vec or "label_id" not in vec:
            continue
        if vec.get("expected_status"):
            continue
        cs = compute_product_label_checksum(
            label_id=vec["label_id"],
            internal_code=vec["internal_code"],
            quantity=vec["quantity"],
        )
        assert cs == vec["checksum"], vec["name"]
        payload = build_product_label_payload(
            label_id=vec["label_id"],
            internal_code=vec["internal_code"],
            quantity=vec["quantity"],
        )
        assert payload == vec["payload"], vec["name"]
        parsed = parse_product_label_payload(payload)
        assert parsed.status is ProductLabelValidationStatus.VALID
        assert parsed.label_id == vec["label_id"]


def test_checksum_failed_tampered() -> None:
    data = _load_vectors()
    vec = next(v for v in data["vectors"] if v["name"] == "checksum-fail-tampered-qty")
    parsed = parse_product_label_payload(vec["tampered_payload"])
    assert parsed.status is ProductLabelValidationStatus.CHECKSUM_FAILED


def test_not_our_format_ean() -> None:
    parsed = parse_product_label_payload("7790001234567")
    assert parsed.status is ProductLabelValidationStatus.NOT_OUR_FORMAT


def test_unknown_version() -> None:
    parsed = parse_product_label_payload("D2|A1B2C3D4E5|SKU100|4|6")
    assert parsed.status is ProductLabelValidationStatus.UNKNOWN_VERSION


@pytest.mark.parametrize(
    "raw,status",
    [
        ("", ProductLabelValidationStatus.MALFORMED),
        ("D1|BAD|SKU|1|A", ProductLabelValidationStatus.NOT_OUR_FORMAT),
    ],
)
def test_malformed_cases(raw: str, status: ProductLabelValidationStatus) -> None:
    assert parse_product_label_payload(raw).status is status
