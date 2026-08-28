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


def _vector_raw(vec: dict) -> str | None:
    if "raw" in vec:
        return vec["raw"]
    if "tampered_payload" in vec:
        return vec["tampered_payload"]
    if "payload" in vec:
        return vec["payload"]
    return None


def _vectors_with_expected_status() -> list[dict]:
    return [v for v in _load_vectors()["vectors"] if v.get("expected_status")]


@pytest.mark.parametrize(
    "vec",
    [pytest.param(v, id=v["name"]) for v in _vectors_with_expected_status() if _vector_raw(v) is not None],
)
def test_shared_vectors_expected_status(vec: dict) -> None:
    raw = _vector_raw(vec)
    assert raw is not None
    parsed = parse_product_label_payload(raw)
    expected = ProductLabelValidationStatus(vec["expected_status"])
    assert parsed.status is expected, (
        f"{vec['name']}: got {parsed.status.value} expected {expected.value}"
    )


def test_all_expected_status_vectors_are_covered() -> None:
    expected = _vectors_with_expected_status()
    covered = [v for v in expected if _vector_raw(v) is not None]
    assert len(covered) == len(expected), (
        f"missing vector raw keys: "
        f"{sorted(v['name'] for v in expected if _vector_raw(v) is None)}"
    )


def test_checksum_vectors_match_contract() -> None:
    data = _load_vectors()
    for vec in data["vectors"]:
        if vec.get("expected_status") != "VALID":
            continue
        if "checksum" not in vec or "label_id" not in vec:
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
        assert parsed.label_id == vec["label_id"].upper()


def test_malformed_empty_raw_vector() -> None:
    vec = next(v for v in _load_vectors()["vectors"] if v["name"] == "malformed-empty")
    assert _vector_raw(vec) == ""
    assert parse_product_label_payload("").status is ProductLabelValidationStatus.MALFORMED


def test_malformed_d1_is_not_not_our_format() -> None:
    parsed = parse_product_label_payload("D1|BAD|X|1|Z")
    assert parsed.status is ProductLabelValidationStatus.MALFORMED


def test_legacy_pipe_remains_not_our_format() -> None:
    parsed = parse_product_label_payload("SKU100|4")
    assert parsed.status is ProductLabelValidationStatus.NOT_OUR_FORMAT
