"""Read-only exact matching between code scan detections and aisle positions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.services.code_scan_normalization import normalize_code_value
from src.application.services.code_scan_qr_payload import extract_qr_payload_lookup_values
from src.application.services.display_primary_product import select_display_primary_product
from src.domain.code_scans.matching import CodeScanMatchStatus, CodeScanMatchType
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord


@dataclass(frozen=True)
class CodeScanMatchOutcome:
    matched_position_id: str | None
    match_status: CodeScanMatchStatus
    match_type: str
    match_confidence: float | None
    match_metadata_json: dict[str, Any] | None


@dataclass(frozen=True)
class _MatchRule:
    match_type: str
    field_name: str


_MATCH_RULES: tuple[_MatchRule, ...] = (
    _MatchRule(CodeScanMatchType.BARCODE_EXACT, "position_barcode"),
    _MatchRule(CodeScanMatchType.SKU_EXACT, "sku"),
    _MatchRule(CodeScanMatchType.INTERNAL_CODE_EXACT, "internal_code"),
    _MatchRule(CodeScanMatchType.POSITION_CODE_EXACT, "corrected_position_code"),
    _MatchRule(CodeScanMatchType.PALLET_ID_EXACT, "pallet_id"),
)

def build_position_lookup(
    positions: list[Position],
    products_by_position: dict[str, list[ProductRecord]],
) -> dict[str, list[tuple[str, str, str]]]:
    """Map normalized code value -> [(position_id, match_type, matched_field), ...]."""
    index: dict[str, list[tuple[str, str, str]]] = {}
    for position in positions:
        if position.status == PositionStatus.DELETED:
            continue
        entries = _position_field_entries(position, products_by_position.get(position.id, ()))
        for norm_value, match_type, field_name in entries:
            index.setdefault(norm_value, []).append((position.id, match_type, field_name))
    return index


def _position_field_entries(
    position: Position,
    products: list[ProductRecord],
) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}

    def add(value: str | None, match_type: str, field_name: str) -> None:
        if not value:
            return
        norm = normalize_code_value(value)
        if not norm:
            return
        entries.append((norm, match_type, field_name))

    add(summary.get("position_barcode") if isinstance(summary.get("position_barcode"), str) else None,
        CodeScanMatchType.BARCODE_EXACT, "position_barcode")
    primary = select_display_primary_product(products) if products else None
    if primary is not None:
        add(primary.sku, CodeScanMatchType.SKU_EXACT, "sku")
    add(summary.get("internal_code") if isinstance(summary.get("internal_code"), str) else None,
        CodeScanMatchType.INTERNAL_CODE_EXACT, "internal_code")
    add(position.corrected_position_code, CodeScanMatchType.POSITION_CODE_EXACT, "corrected_position_code")
    add(summary.get("pallet_id") if isinstance(summary.get("pallet_id"), str) else None,
        CodeScanMatchType.PALLET_ID_EXACT, "pallet_id")
    return entries


def match_detection_value(
    *,
    normalized_code_value: str,
    code_value: str,
    lookup: dict[str, list[tuple[str, str, str]]],
) -> CodeScanMatchOutcome:
    """Evaluate one detection against the aisle lookup (exact, priority-ordered)."""
    outcome = _evaluate_norm_value(normalized_code_value, lookup, report_type_overrides=None)
    if outcome.match_status != CodeScanMatchStatus.NO_MATCH:
        return outcome

    for extra in extract_qr_payload_lookup_values(code_value):
        norm_extra = normalize_code_value(extra)
        if not norm_extra:
            continue
        outcome = _evaluate_norm_value(
            norm_extra,
            lookup,
            report_type_overrides={
                CodeScanMatchType.BARCODE_EXACT: CodeScanMatchType.QR_PAYLOAD_BARCODE_EXACT,
                CodeScanMatchType.SKU_EXACT: CodeScanMatchType.QR_PAYLOAD_SKU_EXACT,
            },
        )
        if outcome.match_status != CodeScanMatchStatus.NO_MATCH:
            return outcome

    return CodeScanMatchOutcome(
        matched_position_id=None,
        match_status=CodeScanMatchStatus.NO_MATCH,
        match_type=CodeScanMatchType.NO_MATCH,
        match_confidence=0.0,
        match_metadata_json=None,
    )


def _evaluate_norm_value(
    norm_value: str,
    lookup: dict[str, list[tuple[str, str, str]]],
    report_type_overrides: dict[str, str] | None,
) -> CodeScanMatchOutcome:
    for rule in _MATCH_RULES:
        report_type = (
            report_type_overrides.get(rule.match_type, rule.match_type)
            if report_type_overrides
            else rule.match_type
        )
        outcome = _match_with_type(
            norm_value,
            rule.match_type,
            rule.field_name,
            lookup,
            report_type=report_type,
        )
        if outcome.match_status != CodeScanMatchStatus.NO_MATCH:
            return outcome
    return CodeScanMatchOutcome(
        matched_position_id=None,
        match_status=CodeScanMatchStatus.NO_MATCH,
        match_type=CodeScanMatchType.NO_MATCH,
        match_confidence=0.0,
        match_metadata_json=None,
    )


def _match_with_type(
    norm_value: str,
    match_type: str,
    field_name: str,
    lookup: dict[str, list[tuple[str, str, str]]],
    *,
    report_type: str | None = None,
) -> CodeScanMatchOutcome:
    hits = [h for h in lookup.get(norm_value, ()) if h[1] == match_type]
    reported = report_type or match_type
    if not hits:
        return CodeScanMatchOutcome(
            matched_position_id=None,
            match_status=CodeScanMatchStatus.NO_MATCH,
            match_type=CodeScanMatchType.NO_MATCH,
            match_confidence=0.0,
            match_metadata_json=None,
        )
    position_ids = list(dict.fromkeys(h[0] for h in hits))
    if len(position_ids) == 1:
        hit = hits[0]
        return CodeScanMatchOutcome(
            matched_position_id=position_ids[0],
            match_status=CodeScanMatchStatus.MATCHED,
            match_type=reported,
            match_confidence=1.0,
            match_metadata_json={
                "matched_field": hit[2],
                "matched_value": norm_value,
            },
        )
    return CodeScanMatchOutcome(
        matched_position_id=None,
        match_status=CodeScanMatchStatus.MULTIPLE_CANDIDATES,
        match_type=CodeScanMatchType.MULTIPLE_CANDIDATES,
        match_confidence=None,
        match_metadata_json={
            "candidate_position_ids": position_ids,
            "matched_field": field_name,
            "matched_value": norm_value,
        },
    )
