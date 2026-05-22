"""Code scan read-only matching enums and match type constants."""

from __future__ import annotations

from enum import Enum


class CodeScanMatchStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    MATCHED = "matched"
    NO_MATCH = "no_match"
    MULTIPLE_CANDIDATES = "multiple_candidates"
    CONFLICT = "conflict"


class CodeScanSummaryMatchStatus:
    """Summary aggregation only — never persisted on individual detections."""

    MIXED = "mixed"


# Allowed detection-level match_status values (DB CHECK + app validation).
DETECTION_MATCH_STATUS_VALUES: frozenset[str] = frozenset(
    s.value for s in CodeScanMatchStatus
)

class CodeScanMatchType:
    """String match type identifiers (exact matching only)."""

    BARCODE_EXACT = "barcode_exact"
    SKU_EXACT = "sku_exact"
    INTERNAL_CODE_EXACT = "internal_code_exact"
    POSITION_CODE_EXACT = "position_code_exact"
    PALLET_ID_EXACT = "pallet_id_exact"
    QR_PAYLOAD_SKU_EXACT = "qr_payload_sku_exact"
    QR_PAYLOAD_BARCODE_EXACT = "qr_payload_barcode_exact"
    MULTIPLE_CANDIDATES = "multiple_candidates"
    NO_MATCH = "no_match"


DETECTION_MATCH_TYPE_VALUES: frozenset[str] = frozenset(
    {
        CodeScanMatchType.BARCODE_EXACT,
        CodeScanMatchType.SKU_EXACT,
        CodeScanMatchType.INTERNAL_CODE_EXACT,
        CodeScanMatchType.POSITION_CODE_EXACT,
        CodeScanMatchType.PALLET_ID_EXACT,
        CodeScanMatchType.QR_PAYLOAD_SKU_EXACT,
        CodeScanMatchType.QR_PAYLOAD_BARCODE_EXACT,
        CodeScanMatchType.MULTIPLE_CANDIDATES,
        CodeScanMatchType.NO_MATCH,
    }
)


def validate_detection_match_fields(
    *,
    match_status: str | None,
    match_type: str | None,
) -> None:
    if match_status is not None and match_status not in DETECTION_MATCH_STATUS_VALUES:
        raise ValueError(f"invalid code scan match_status: {match_status}")
    if match_type is not None and match_type not in DETECTION_MATCH_TYPE_VALUES:
        raise ValueError(f"invalid code scan match_type: {match_type}")
