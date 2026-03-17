"""v3.2.2 — Central quantity resolution.

This module is the single source of truth for:
- normalized qty parse states
- qty provenance (source + inference reason)
- the minimum-count inference rule (qty_final=1)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class QtyParseStatus(str, Enum):
    MISSING = "missing"  # field absent
    NULL = "null"  # field explicitly null
    INVALID = "invalid"  # not parseable as integer
    ZERO = "zero"  # explicit 0
    VALID_POSITIVE = "valid_positive"  # integer >= 1


class QtySource(str, Enum):
    DETECTED = "detected"
    INFERRED = "inferred"
    # Internal-only distinction (optional). If not used, keep DETECTED.
    CONSOLIDATED = "consolidated"


class QtyInferenceReason(str, Enum):
    VALID_EVIDENCE_WITHOUT_EXPLICIT_QUANTITY = "valid_evidence_without_explicit_quantity"


@dataclass(frozen=True)
class NormalizedQty:
    raw_qty: Any
    parse_status: QtyParseStatus
    explicit_qty: Optional[int]


@dataclass(frozen=True)
class QtyResolution:
    """Result of central quantity resolution. Authoritative for persistence and API."""

    qty_final: int
    qty_source: QtySource
    qty_inference_reason: Optional[QtyInferenceReason]
    raw_qty: Any
    qty_parse_status: QtyParseStatus
    normalization_notes: Optional[str] = None
    # When False, this resolution is "unresolved / not materialized"; qty_final=0 must not
    # be treated as a valid visible quantity for product-present entities.
    is_resolved: bool = True


def normalize_raw_qty(raw_qty: Any, *, field_was_present: bool) -> NormalizedQty:
    """Normalize a raw qty value into a typed state.

    Notes:
    - We treat negative values as INVALID (domain does not accept negative quantities).
    - Strings are accepted if they parse cleanly to an int.
    """
    if not field_was_present:
        return NormalizedQty(raw_qty=None, parse_status=QtyParseStatus.MISSING, explicit_qty=None)
    if raw_qty is None:
        return NormalizedQty(raw_qty=None, parse_status=QtyParseStatus.NULL, explicit_qty=None)

    try:
        if isinstance(raw_qty, bool):
            raise ValueError("bool is not a valid qty")
        qty_int = int(str(raw_qty).strip()) if isinstance(raw_qty, str) else int(raw_qty)
    except Exception:
        return NormalizedQty(raw_qty=raw_qty, parse_status=QtyParseStatus.INVALID, explicit_qty=None)

    if qty_int < 0:
        return NormalizedQty(raw_qty=raw_qty, parse_status=QtyParseStatus.INVALID, explicit_qty=None)
    if qty_int == 0:
        return NormalizedQty(raw_qty=raw_qty, parse_status=QtyParseStatus.ZERO, explicit_qty=0)
    return NormalizedQty(raw_qty=raw_qty, parse_status=QtyParseStatus.VALID_POSITIVE, explicit_qty=qty_int)


def resolve_final_qty(
    *,
    has_valid_evidence: bool,
    is_product_present: bool,
    normalized_qty: NormalizedQty,
    explicit_consolidated_qty: Optional[int] = None,
    allow_zero_as_valid: bool = False,
) -> QtyResolution:
    """Resolve final qty with provenance using v3.2.2 rule set.

    Priority order:
    1) valid explicit detected quantity
    2) valid consolidated quantity from explicit sources
    3) inferred minimum quantity = 1 (only when evidence is valid and product-present)
    4) otherwise, return 0 (unresolved / not materialized as counted)
    """
    # (1) explicit detected quantity
    if normalized_qty.parse_status == QtyParseStatus.VALID_POSITIVE and normalized_qty.explicit_qty is not None:
        return QtyResolution(
            qty_final=normalized_qty.explicit_qty,
            qty_source=QtySource.DETECTED,
            qty_inference_reason=None,
            raw_qty=normalized_qty.raw_qty,
            qty_parse_status=normalized_qty.parse_status,
            is_resolved=True,
        )

    # (2) explicit consolidated qty (if caller provides one)
    if explicit_consolidated_qty is not None and explicit_consolidated_qty >= 1:
        return QtyResolution(
            qty_final=int(explicit_consolidated_qty),
            qty_source=QtySource.CONSOLIDATED,
            qty_inference_reason=None,
            raw_qty=normalized_qty.raw_qty,
            qty_parse_status=normalized_qty.parse_status,
            normalization_notes="used_consolidated_qty",
            is_resolved=True,
        )

    # Interpret zero: invalid unless explicitly allowed by a separate business rule.
    if normalized_qty.parse_status == QtyParseStatus.ZERO and allow_zero_as_valid:
        return QtyResolution(
            qty_final=0,
            qty_source=QtySource.DETECTED,
            qty_inference_reason=None,
            raw_qty=normalized_qty.raw_qty,
            qty_parse_status=normalized_qty.parse_status,
            normalization_notes="zero_allowed_by_rule",
            is_resolved=True,
        )

    # (3) minimum inferred qty
    if has_valid_evidence and is_product_present:
        return QtyResolution(
            qty_final=1,
            qty_source=QtySource.INFERRED,
            qty_inference_reason=QtyInferenceReason.VALID_EVIDENCE_WITHOUT_EXPLICIT_QUANTITY,
            raw_qty=normalized_qty.raw_qty,
            qty_parse_status=normalized_qty.parse_status,
            is_resolved=True,
        )

    # (4) Unresolved / not materialized. Callers must not treat qty_final as valid visible
    # quantity for product-present entities; persist as unresolved for audit.
    return QtyResolution(
        qty_final=0,
        qty_source=QtySource.DETECTED,
        qty_inference_reason=None,
        raw_qty=normalized_qty.raw_qty,
        qty_parse_status=normalized_qty.parse_status,
        normalization_notes="no_inference_due_to_insufficient_evidence_or_presence",
        is_resolved=False,
    )

