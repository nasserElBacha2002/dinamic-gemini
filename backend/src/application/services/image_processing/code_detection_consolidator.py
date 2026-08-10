"""Phase 3+ — consolidate product code detections into 0..N physical labels per image.

Physical product labels (format D1) dedupe by ``label_id`` only.

Legacy PIPE/DI1 payloads (no label_id) keep prior single-logical-code behavior when no
D1 labels are present. When D1 and legacy mix, D1 wins for counted results; legacy codes
are recorded as NOT_OUR_FORMAT / legacy warnings (no invented label_id).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.application.services.image_processing.encoded_label_payload_parser import (
    ParsedLabelPayload,
)
from src.domain.product_labels.format import (
    ParsedProductLabelPayload,
    ProductLabelValidationStatus,
    parse_product_label_payload,
)


class CodeConsolidationStatus(str, Enum):
    NO_DETECTIONS = "NO_DETECTIONS"
    NO_VALID_CODE = "NO_VALID_CODE"
    RESOLVED = "RESOLVED"
    MISSING_QUANTITY = "MISSING_QUANTITY"
    QUANTITY_CONFLICT = "QUANTITY_CONFLICT"
    MULTIPLE_DISTINCT_CODES = "MULTIPLE_DISTINCT_CODES"
    # Multi-product D1 path: one or more valid physical labels.
    RESOLVED_MULTI = "RESOLVED_MULTI"


@dataclass(frozen=True)
class CodeDetectionInput:
    symbology: str
    raw_value: str
    parsed: ParsedLabelPayload
    bounding_box: dict | None = None
    detection_index: int = 0


@dataclass(frozen=True)
class ProductLabelResult:
    """One counted physical product label from an image (after intra-image dedupe)."""

    label_id: str
    internal_code: str
    quantity: int
    format_version: str
    checksum: str
    validation_status: str
    selected_detection_index: int
    duplicate_detection_count: int = 1
    symbology: str | None = None
    raw_payload: str | None = None
    normalized_payload: str | None = None


@dataclass(frozen=True)
class ProductLabelRejection:
    validation_status: str
    raw_value: str
    detection_index: int
    label_id: str | None = None
    detail: str | None = None
    symbology: str | None = None


@dataclass(frozen=True)
class CodeConsolidationResult:
    status: CodeConsolidationStatus
    internal_code: str | None = None
    quantity: int | None = None
    selected_detection_index: int | None = None
    distinct_codes: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    # New: 0..N D1 physical labels (preferred path).
    product_results: tuple[ProductLabelResult, ...] = field(default_factory=tuple)
    rejections: tuple[ProductLabelRejection, ...] = field(default_factory=tuple)


class CodeDetectionConsolidator:
    """Collapse per-image detections into 0..N deterministic product labels."""

    def consolidate(
        self, detections: list[CodeDetectionInput]
    ) -> CodeConsolidationResult:
        if not detections:
            return CodeConsolidationResult(status=CodeConsolidationStatus.NO_DETECTIONS)

        d1_by_label: dict[str, list[tuple[CodeDetectionInput, ParsedProductLabelPayload]]] = {}
        rejections: list[ProductLabelRejection] = []
        has_d1_attempt = False

        for det in detections:
            d1 = parse_product_label_payload(det.raw_value)
            if d1.status is ProductLabelValidationStatus.NOT_OUR_FORMAT:
                continue
            has_d1_attempt = True
            if d1.status is ProductLabelValidationStatus.VALID and d1.label_id and d1.internal_code and d1.quantity:
                d1_by_label.setdefault(d1.label_id, []).append((det, d1))
            else:
                rejections.append(
                    ProductLabelRejection(
                        validation_status=d1.status.value,
                        raw_value=det.raw_value,
                        detection_index=det.detection_index,
                        label_id=d1.label_id,
                        detail=d1.detail,
                        symbology=det.symbology,
                    )
                )

        if d1_by_label:
            products: list[ProductLabelResult] = []
            # Stable order: first-seen label_id order.
            for label_id, group in d1_by_label.items():
                first_det, first_parsed = group[0]
                # Quantity/code conflict for same label_id → reject that label.
                codes = {p.internal_code for _, p in group}
                qtys = {p.quantity for _, p in group}
                if len(codes) > 1 or len(qtys) > 1:
                    rejections.append(
                        ProductLabelRejection(
                            validation_status="QUANTITY_CONFLICT",
                            raw_value=first_det.raw_value,
                            detection_index=first_det.detection_index,
                            label_id=label_id,
                            detail="conflicting payloads for same label_id",
                            symbology=first_det.symbology,
                        )
                    )
                    continue
                internal_code = first_parsed.internal_code
                quantity = first_parsed.quantity
                if internal_code is None or quantity is None:
                    continue
                products.append(
                    ProductLabelResult(
                        label_id=label_id,
                        internal_code=str(internal_code),
                        quantity=int(quantity),
                        format_version=str(first_parsed.format_version),
                        checksum=str(first_parsed.checksum_received),
                        validation_status=ProductLabelValidationStatus.VALID.value,
                        selected_detection_index=first_det.detection_index,
                        duplicate_detection_count=len(group),
                        symbology=first_det.symbology,
                        raw_payload=first_det.raw_value,
                        normalized_payload=first_parsed.normalized_payload,
                    )
                )

            if not products:
                return CodeConsolidationResult(
                    status=CodeConsolidationStatus.NO_VALID_CODE,
                    warnings=("NO_VALID_D1_PRODUCT_LABEL",),
                    rejections=tuple(rejections),
                )

            primary = products[0]
            status = (
                CodeConsolidationStatus.RESOLVED_MULTI
                if len(products) > 1
                else CodeConsolidationStatus.RESOLVED
            )
            warnings: list[str] = []
            if len(products) > 1:
                warnings.append("MULTI_PRODUCT_IMAGE")
            if rejections:
                warnings.append("D1_PARTIAL_REJECTIONS")
            return CodeConsolidationResult(
                status=status,
                internal_code=primary.internal_code,
                quantity=primary.quantity,
                selected_detection_index=primary.selected_detection_index,
                distinct_codes=tuple(p.internal_code for p in products),
                warnings=tuple(warnings),
                product_results=tuple(products),
                rejections=tuple(rejections),
            )

        if has_d1_attempt:
            # Any recognized Dinamic D1 attempt (even if all invalid) blocks legacy revive.
            return CodeConsolidationResult(
                status=CodeConsolidationStatus.NO_VALID_CODE,
                warnings=("D1_CANDIDATES_FAILED",),
                rejections=tuple(rejections),
            )

        # ---- Legacy path (no D1 labels): preserve prior ≤1 logical code semantics ----
        return self._consolidate_legacy(detections, rejections=rejections)

    def _consolidate_legacy(
        self,
        detections: list[CodeDetectionInput],
        *,
        rejections: list[ProductLabelRejection],
    ) -> CodeConsolidationResult:
        with_code = [d for d in detections if d.parsed.internal_code]
        if not with_code:
            return CodeConsolidationResult(
                status=CodeConsolidationStatus.NO_VALID_CODE,
                rejections=tuple(rejections),
            )

        grouped: dict[str, list[CodeDetectionInput]] = {}
        for det in with_code:
            grouped.setdefault(det.parsed.internal_code, []).append(det)  # type: ignore[arg-type]

        distinct_codes = tuple(grouped.keys())
        if len(distinct_codes) > 1:
            return CodeConsolidationResult(
                status=CodeConsolidationStatus.MULTIPLE_DISTINCT_CODES,
                distinct_codes=distinct_codes,
                warnings=("MULTIPLE_DISTINCT_CODES", "LEGACY_NO_LABEL_ID"),
                rejections=tuple(rejections),
            )

        code = distinct_codes[0]
        group = grouped[code]
        quantities = {d.parsed.quantity for d in group if d.parsed.quantity is not None}
        if len(quantities) > 1:
            return CodeConsolidationResult(
                status=CodeConsolidationStatus.QUANTITY_CONFLICT,
                internal_code=code,
                distinct_codes=distinct_codes,
                warnings=("QUANTITY_CONFLICT", "LEGACY_NO_LABEL_ID"),
                rejections=tuple(rejections),
            )

        if not quantities:
            return CodeConsolidationResult(
                status=CodeConsolidationStatus.MISSING_QUANTITY,
                internal_code=code,
                selected_detection_index=group[0].detection_index,
                distinct_codes=distinct_codes,
                warnings=("QUANTITY_MISSING", "LEGACY_NO_LABEL_ID"),
                rejections=tuple(rejections),
            )

        quantity = next(iter(quantities))
        selected = next((d for d in group if d.parsed.quantity == quantity), group[0])
        return CodeConsolidationResult(
            status=CodeConsolidationStatus.RESOLVED,
            internal_code=code,
            quantity=quantity,
            selected_detection_index=selected.detection_index,
            distinct_codes=distinct_codes,
            warnings=("LEGACY_NO_LABEL_ID",),
            rejections=tuple(rejections),
        )


__all__ = [
    "CodeConsolidationResult",
    "CodeConsolidationStatus",
    "CodeDetectionConsolidator",
    "CodeDetectionInput",
    "ProductLabelRejection",
    "ProductLabelResult",
]
