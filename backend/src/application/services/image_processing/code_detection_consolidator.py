"""Phase 3 — consolidate multiple code detections from one image into one logical label.

Physical rule: ONE image → at most ONE position. This consolidator collapses repeated
detections of the same code (e.g. a QR + a CODE128 encoding the same ``code|qty``, or the
same symbol decoded twice) into a single logical label, and flags ambiguity for manual
review instead of guessing.

Guarantees:
- Same raw value / same parsed ``(code, quantity)`` → one logical label.
- Distinct internal codes across detections → ``MULTIPLE_DISTINCT_CODES`` (manual review).
- Never merges the code of one detection with the quantity of a different code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.application.services.image_processing.encoded_label_payload_parser import (
    ParsedLabelPayload,
)


class CodeConsolidationStatus(str, Enum):
    NO_DETECTIONS = "NO_DETECTIONS"
    NO_VALID_CODE = "NO_VALID_CODE"
    RESOLVED = "RESOLVED"
    MISSING_QUANTITY = "MISSING_QUANTITY"
    QUANTITY_CONFLICT = "QUANTITY_CONFLICT"
    MULTIPLE_DISTINCT_CODES = "MULTIPLE_DISTINCT_CODES"


@dataclass(frozen=True)
class CodeDetectionInput:
    symbology: str
    raw_value: str
    parsed: ParsedLabelPayload
    bounding_box: dict | None = None
    detection_index: int = 0


@dataclass(frozen=True)
class CodeConsolidationResult:
    status: CodeConsolidationStatus
    internal_code: str | None = None
    quantity: int | None = None
    selected_detection_index: int | None = None
    distinct_codes: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


class CodeDetectionConsolidator:
    """Collapse per-image detections into a single deterministic logical label."""

    def consolidate(
        self, detections: list[CodeDetectionInput]
    ) -> CodeConsolidationResult:
        if not detections:
            return CodeConsolidationResult(status=CodeConsolidationStatus.NO_DETECTIONS)

        with_code = [d for d in detections if d.parsed.internal_code]
        if not with_code:
            return CodeConsolidationResult(status=CodeConsolidationStatus.NO_VALID_CODE)

        # Group by internal code; preserve first-seen order for determinism.
        grouped: dict[str, list[CodeDetectionInput]] = {}
        for det in with_code:
            grouped.setdefault(det.parsed.internal_code, []).append(det)  # type: ignore[arg-type]

        distinct_codes = tuple(grouped.keys())
        if len(distinct_codes) > 1:
            return CodeConsolidationResult(
                status=CodeConsolidationStatus.MULTIPLE_DISTINCT_CODES,
                distinct_codes=distinct_codes,
                warnings=("MULTIPLE_DISTINCT_CODES",),
            )

        code = distinct_codes[0]
        group = grouped[code]

        # Never merge a quantity across different codes: quantities considered here all
        # belong to detections of this single code.
        quantities = {d.parsed.quantity for d in group if d.parsed.quantity is not None}
        if len(quantities) > 1:
            return CodeConsolidationResult(
                status=CodeConsolidationStatus.QUANTITY_CONFLICT,
                internal_code=code,
                distinct_codes=distinct_codes,
                warnings=("QUANTITY_CONFLICT",),
            )

        if not quantities:
            return CodeConsolidationResult(
                status=CodeConsolidationStatus.MISSING_QUANTITY,
                internal_code=code,
                selected_detection_index=group[0].detection_index,
                distinct_codes=distinct_codes,
                warnings=("QUANTITY_MISSING",),
            )

        quantity = next(iter(quantities))
        selected = next(
            (d for d in group if d.parsed.quantity == quantity), group[0]
        )
        return CodeConsolidationResult(
            status=CodeConsolidationStatus.RESOLVED,
            internal_code=code,
            quantity=quantity,
            selected_detection_index=selected.detection_index,
            distinct_codes=distinct_codes,
        )


__all__ = [
    "CodeConsolidationResult",
    "CodeConsolidationStatus",
    "CodeDetectionConsolidator",
    "CodeDetectionInput",
]
