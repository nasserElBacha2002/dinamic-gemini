"""Unit tests for read-only code scan result matching."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.code_scan_qr_payload import extract_qr_payload_lookup_values
from src.application.services.code_scan_result_matcher import (
    build_position_lookup,
    match_detection_value,
)
from src.domain.code_scans.matching import CodeScanMatchStatus, CodeScanMatchType
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord


def _position(
    position_id: str,
    *,
    summary: dict | None = None,
    corrected_position_code: str | None = None,
) -> Position:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    return Position(
        id=position_id,
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json=summary,
        corrected_position_code=corrected_position_code,
    )


def _product(position_id: str, sku: str) -> ProductRecord:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    return ProductRecord(
        id=f"prod-{position_id}",
        position_id=position_id,
        sku=sku,
        detected_quantity=1,
        confidence=0.9,
        created_at=now,
        updated_at=now,
    )


def test_barcode_exact_single_match() -> None:
    positions = [_position("p1", summary={"position_barcode": "7791234567890"})]
    lookup = build_position_lookup(positions, {})
    outcome = match_detection_value(
        normalized_code_value="7791234567890",
        code_value="7791234567890",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MATCHED
    assert outcome.matched_position_id == "p1"
    assert outcome.match_type == CodeScanMatchType.BARCODE_EXACT


def test_sku_exact_single_match() -> None:
    positions = [_position("p1")]
    products = {"p1": [_product("p1", "3075807")]}
    lookup = build_position_lookup(positions, products)
    outcome = match_detection_value(
        normalized_code_value="3075807",
        code_value="3075807",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MATCHED
    assert outcome.match_type == CodeScanMatchType.SKU_EXACT


def test_leading_zeros_preserved() -> None:
    positions = [_position("p1", summary={"position_barcode": "00123"})]
    lookup = build_position_lookup(positions, {})
    outcome = match_detection_value(
        normalized_code_value="00123",
        code_value="00123",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MATCHED
    assert outcome.matched_position_id == "p1"


def test_multiple_candidates() -> None:
    positions = [
        _position("p1", summary={"position_barcode": "SAME"}),
        _position("p2", summary={"position_barcode": "SAME"}),
    ]
    lookup = build_position_lookup(positions, {})
    outcome = match_detection_value(
        normalized_code_value="SAME",
        code_value="SAME",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MULTIPLE_CANDIDATES
    assert outcome.matched_position_id is None
    assert outcome.match_metadata_json is not None
    assert set(outcome.match_metadata_json["candidate_position_ids"]) == {"p1", "p2"}


def test_no_match() -> None:
    lookup = build_position_lookup([_position("p1", summary={"position_barcode": "A"})], {})
    outcome = match_detection_value(
        normalized_code_value="B",
        code_value="B",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.NO_MATCH
    assert outcome.match_confidence == 0.0


def test_secondary_product_sku_matches() -> None:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    position = _position("p1")
    products = [
        _product("p1", "SKU-A"),
        ProductRecord(
            id="prod-b",
            position_id="p1",
            sku="SKU-B",
            detected_quantity=1,
            confidence=0.8,
            created_at=now,
            updated_at=now,
        ),
    ]
    lookup = build_position_lookup([position], {"p1": products})
    outcome = match_detection_value(
        normalized_code_value="SKU-B",
        code_value="SKU-B",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MATCHED
    assert outcome.matched_position_id == "p1"
    assert outcome.match_type == CodeScanMatchType.SKU_EXACT


def test_internal_code_exact_from_summary() -> None:
    positions = [_position("p1", summary={"internal_code": "IC-99"})]
    lookup = build_position_lookup(positions, {})
    outcome = match_detection_value(
        normalized_code_value="IC-99",
        code_value="IC-99",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MATCHED
    assert outcome.match_type == CodeScanMatchType.INTERNAL_CODE_EXACT


def test_pallet_id_exact_from_summary() -> None:
    positions = [_position("p1", summary={"pallet_id": "PAL-42"})]
    lookup = build_position_lookup(positions, {})
    outcome = match_detection_value(
        normalized_code_value="PAL-42",
        code_value="PAL-42",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MATCHED
    assert outcome.match_type == CodeScanMatchType.PALLET_ID_EXACT


def test_position_code_exact_from_corrected_field() -> None:
    positions = [_position("p1", corrected_position_code="POS-7")]
    lookup = build_position_lookup(positions, {})
    outcome = match_detection_value(
        normalized_code_value="POS-7",
        code_value="POS-7",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MATCHED
    assert outcome.match_type == CodeScanMatchType.POSITION_CODE_EXACT


def test_qr_payload_sku_extraction() -> None:
    assert extract_qr_payload_lookup_values("SKU=3075807") == ("3075807",)
    positions = [_position("p1")]
    products = {"p1": [_product("p1", "3075807")]}
    lookup = build_position_lookup(positions, products)
    outcome = match_detection_value(
        normalized_code_value="SKU=3075807",
        code_value="SKU=3075807",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MATCHED
    assert outcome.match_type == CodeScanMatchType.QR_PAYLOAD_SKU_EXACT


def test_inventory_pipe_and_di1_payload_lookup() -> None:
    from src.application.services.code_scan_qr_payload import parse_inventory_code_payload

    assert extract_qr_payload_lookup_values("22294029014|234") == ("22294029014",)
    assert extract_qr_payload_lookup_values("DI1|C=32535235|Q=909") == ("32535235",)
    assert parse_inventory_code_payload("22294029014|234") == {
        "internal_code": "22294029014",
        "quantity": 234,
    }
    assert parse_inventory_code_payload("32535235") == {
        "internal_code": "32535235",
        "quantity": None,
    }

    positions = [_position("p1")]
    # Match via internal_code extracted from pipe payload
    products: dict = {"p1": []}
    lookup = build_position_lookup(positions, products)
    # Seed lookup with internal code as if present on position summary
    lookup.setdefault("22294029014", [("p1", CodeScanMatchType.INTERNAL_CODE_EXACT, "internal_code")])
    outcome = match_detection_value(
        normalized_code_value="22294029014|234",
        code_value="22294029014|234",
        lookup=lookup,
    )
    assert outcome.match_status == CodeScanMatchStatus.MATCHED
    assert outcome.matched_position_id == "p1"
