"""Resolve scanned D1 payloads against issued_product_labels (authoritative registry).

Parser remains I/O-free; this service owns registry lookups and client/payload matching.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.issued_product_label_repository import IssuedProductLabelRepository
from src.domain.product_labels.format import (
    ParsedProductLabelPayload,
    ProductLabelValidationStatus,
    build_product_label_payload,
    compute_product_label_checksum,
)
from src.domain.product_labels.processed import (
    ProcessedProductLabel,
    ProductLabelOutcomeStatus,
)


@dataclass(frozen=True)
class IssuedProductLabelResolveResult:
    status: ProductLabelOutcomeStatus
    product: ProcessedProductLabel | None = None
    detail: str | None = None


class IssuedProductLabelResolver:
    def __init__(self, *, issued_repo: IssuedProductLabelRepository) -> None:
        self._issued = issued_repo

    def resolve_parsed(
        self,
        *,
        parsed: ParsedProductLabelPayload,
        expected_client_id: str,
        selected_detection_index: int | None = None,
        duplicate_detection_count: int = 1,
        symbology: str | None = None,
    ) -> IssuedProductLabelResolveResult:
        if parsed.status is ProductLabelValidationStatus.CHECKSUM_FAILED:
            return IssuedProductLabelResolveResult(
                status=ProductLabelOutcomeStatus.CHECKSUM_FAILED,
                product=ProcessedProductLabel(
                    label_id=parsed.label_id,
                    internal_code=parsed.internal_code,
                    quantity=parsed.quantity,
                    format_version=parsed.format_version,
                    checksum=parsed.checksum_received,
                    validation_status=ProductLabelOutcomeStatus.CHECKSUM_FAILED,
                    selected_detection_index=selected_detection_index,
                    duplicate_detection_count=duplicate_detection_count,
                    symbology=symbology,
                    raw_payload=parsed.raw_value,
                    normalized_payload=parsed.normalized_payload,
                    detail=parsed.detail,
                ),
                detail=parsed.detail,
            )
        if parsed.status is ProductLabelValidationStatus.UNKNOWN_VERSION:
            return IssuedProductLabelResolveResult(
                status=ProductLabelOutcomeStatus.UNKNOWN_VERSION,
                detail=parsed.detail,
            )
        if parsed.status is ProductLabelValidationStatus.MALFORMED:
            return IssuedProductLabelResolveResult(
                status=ProductLabelOutcomeStatus.MALFORMED,
                detail=parsed.detail,
            )
        if parsed.status is not ProductLabelValidationStatus.VALID:
            return IssuedProductLabelResolveResult(
                status=ProductLabelOutcomeStatus.NOT_OUR_FORMAT,
                detail=parsed.detail,
            )

        label_id = (parsed.label_id or "").strip().upper()
        expected_client = (expected_client_id or "").strip()
        if not label_id or not expected_client:
            return IssuedProductLabelResolveResult(
                status=ProductLabelOutcomeStatus.MALFORMED,
                detail="missing label_id or client_id",
            )

        issued = self._issued.get_by_label_id(label_id)
        if issued is None:
            return IssuedProductLabelResolveResult(
                status=ProductLabelOutcomeStatus.UNKNOWN_LABEL,
                product=ProcessedProductLabel(
                    label_id=label_id,
                    internal_code=parsed.internal_code,
                    quantity=parsed.quantity,
                    format_version=parsed.format_version,
                    checksum=parsed.checksum_received,
                    validation_status=ProductLabelOutcomeStatus.UNKNOWN_LABEL,
                    selected_detection_index=selected_detection_index,
                    duplicate_detection_count=duplicate_detection_count,
                    symbology=symbology,
                    raw_payload=parsed.raw_value,
                    normalized_payload=parsed.normalized_payload,
                    detail="label_id not issued",
                ),
                detail="label_id not issued",
            )

        if (issued.client_id or "").strip() != expected_client:
            return IssuedProductLabelResolveResult(
                status=ProductLabelOutcomeStatus.CLIENT_MISMATCH,
                product=ProcessedProductLabel(
                    label_id=label_id,
                    internal_code=None,
                    quantity=None,
                    format_version=issued.format_version,
                    checksum=None,
                    validation_status=ProductLabelOutcomeStatus.CLIENT_MISMATCH,
                    selected_detection_index=selected_detection_index,
                    duplicate_detection_count=duplicate_detection_count,
                    symbology=symbology,
                    raw_payload=parsed.raw_value,
                    detail="product label belongs to another client",
                ),
                detail="product label belongs to another client",
            )

        # Authoritative fields from issued registry (SoT).
        auth_code = (issued.internal_code or "").strip()
        auth_qty = int(issued.quantity)
        auth_version = (issued.format_version or "").strip() or "D1"
        auth_checksum = compute_product_label_checksum(
            label_id=label_id,
            internal_code=auth_code,
            quantity=auth_qty,
            format_version=auth_version,
        )
        auth_payload = build_product_label_payload(
            label_id=label_id,
            internal_code=auth_code,
            quantity=auth_qty,
            format_version=auth_version,
        )

        scan_code = (parsed.internal_code or "").strip()
        scan_qty = parsed.quantity
        scan_version = (parsed.format_version or "").strip()
        scan_checksum = (parsed.checksum_received or "").strip().upper()
        scan_norm = (parsed.normalized_payload or "").strip()

        if (
            scan_code != auth_code
            or scan_qty != auth_qty
            or scan_version.upper() != auth_version.upper()
            or scan_checksum != auth_checksum
            or (scan_norm and scan_norm != auth_payload)
            or (issued.payload or "").strip() != auth_payload
        ):
            return IssuedProductLabelResolveResult(
                status=ProductLabelOutcomeStatus.PAYLOAD_MISMATCH,
                product=ProcessedProductLabel(
                    label_id=label_id,
                    internal_code=auth_code,
                    quantity=auth_qty,
                    format_version=auth_version,
                    checksum=auth_checksum,
                    validation_status=ProductLabelOutcomeStatus.PAYLOAD_MISMATCH,
                    selected_detection_index=selected_detection_index,
                    duplicate_detection_count=duplicate_detection_count,
                    symbology=symbology,
                    raw_payload=parsed.raw_value,
                    normalized_payload=auth_payload,
                    detail="scanned payload does not match issued registry",
                ),
                detail="scanned payload does not match issued registry",
            )

        return IssuedProductLabelResolveResult(
            status=ProductLabelOutcomeStatus.VALID,
            product=ProcessedProductLabel(
                label_id=label_id,
                internal_code=auth_code,
                quantity=auth_qty,
                format_version=auth_version,
                checksum=auth_checksum,
                validation_status=ProductLabelOutcomeStatus.VALID,
                selected_detection_index=selected_detection_index,
                duplicate_detection_count=duplicate_detection_count,
                symbology=symbology,
                raw_payload=parsed.raw_value,
                normalized_payload=auth_payload,
            ),
        )


__all__ = [
    "IssuedProductLabelResolveResult",
    "IssuedProductLabelResolver",
]
