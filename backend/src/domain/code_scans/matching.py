"""Code scan read-only matching enums and match type constants."""

from __future__ import annotations

from enum import Enum


class CodeScanMatchStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    MATCHED = "matched"
    NO_MATCH = "no_match"
    MULTIPLE_CANDIDATES = "multiple_candidates"
    CONFLICT = "conflict"


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
