"""
Epic 3.1.D — Centralized review display label derivation.

Single source of truth for the display label used in review/audit and export.
Semantics: review-oriented label that prefers internal_code (product/SKU from product label),
then falls back to position_barcode (position/pallet identifier). Not guaranteed to be
product-only; it is the best single identifier for display in review/export contexts.
"""

from typing import Optional


def _normalize_optional_str(value: Optional[str]) -> str:
    """Return stripped string; None and whitespace-only become empty string."""
    if value is None:
        return ""
    return (value or "").strip()


def derive_review_display_label(
    internal_code: Optional[str] = None,
    position_barcode: Optional[str] = None,
) -> Optional[str]:
    """Derive the single review/export display label for an entity.

    Prefers internal_code (product/SKU from product label), then position_barcode
    (position/pallet barcode). None, empty string, and whitespace-only are treated
    as missing and trigger fallback to the other field.

    Use this helper in report shaping, API shaping, and CSV export so semantics
    stay consistent and derivation logic is not duplicated.

    Returns:
        First non-empty of (internal_code, position_barcode) after normalizing,
        or None if both are missing/blank.
    """
    ic = _normalize_optional_str(internal_code)
    pb = _normalize_optional_str(position_barcode)
    return ic or pb or None
