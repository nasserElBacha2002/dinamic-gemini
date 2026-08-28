"""Map authoritative local CODE_SCAN rows to ProcessedProductLabel (D1 trust boundary).

Mobile authoritative rows are operator-confirmed on device. Backend does **not** treat
``label_id`` alphabet validation as server-side D1 proof. For ``LOCAL_CODE_SCAN`` with
``label_id``, we rebuild the canonical D1 payload, parse it, and resolve against the
issued-label registry (same components as CV/TXT productive paths).

``LOCAL_MANUAL_CORRECTION`` never consumes a counted-label claim: ``label_id`` is ignored.
Historical rows without ``label_id`` keep the legacy apply path (including missing quantity
→ review via ``legacy_missing_quantity``).
"""

from __future__ import annotations

from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.domain.authoritative_local_code_scan.entities import (
    AuthoritativeLocalCodeScanResult,
    AuthoritativeQuantityStatus,
    AuthoritativeResultSource,
)
from src.domain.product_labels.format import (
    ProductLabelValidationStatus,
    build_product_label_payload,
    parse_product_label_payload,
)
from src.domain.product_labels.processed import (
    ProcessedProductLabel,
    ProductLabelOutcomeStatus,
)

_PARSE_STATUS_TO_OUTCOME: dict[ProductLabelValidationStatus, ProductLabelOutcomeStatus] = {
    ProductLabelValidationStatus.CHECKSUM_FAILED: ProductLabelOutcomeStatus.CHECKSUM_FAILED,
    ProductLabelValidationStatus.UNKNOWN_VERSION: ProductLabelOutcomeStatus.UNKNOWN_VERSION,
    ProductLabelValidationStatus.MALFORMED: ProductLabelOutcomeStatus.MALFORMED,
    ProductLabelValidationStatus.QUANTITY_INVALID: ProductLabelOutcomeStatus.QUANTITY_INVALID,
    ProductLabelValidationStatus.LABEL_ID_INVALID: ProductLabelOutcomeStatus.LABEL_ID_INVALID,
    ProductLabelValidationStatus.NOT_OUR_FORMAT: ProductLabelOutcomeStatus.NOT_OUR_FORMAT,
}


def build_product_results_for_authoritative_row(
    row: AuthoritativeLocalCodeScanResult,
    *,
    client_id: str,
    issued_resolver: IssuedProductLabelResolver | None,
) -> list[ProcessedProductLabel]:
    code = (row.internal_code or "").strip()
    if not code:
        return []

    source = (row.source or "").strip().upper()
    qty_status = (row.quantity_status or "").strip().upper()
    label_id = (row.label_id or "").strip().upper() or None

    if source == AuthoritativeResultSource.LOCAL_MANUAL_CORRECTION.value:
        return _legacy_manual_correction(code=code, row=row, qty_status=qty_status)

    if label_id is None:
        return _legacy_code_scan(code=code, row=row, qty_status=qty_status)

    return _d1_code_scan(
        code=code,
        label_id=label_id,
        row=row,
        qty_status=qty_status,
        client_id=client_id,
        issued_resolver=issued_resolver,
    )


def authoritative_blocks_legacy_persist_fallback(
    row: AuthoritativeLocalCodeScanResult,
    product_results: list[ProcessedProductLabel],
) -> bool:
    """When D1 claim was attempted but no VALID product, block legacy qty=0 fallback."""
    label_id = (row.label_id or "").strip().upper() or None
    source = (row.source or "").strip().upper()
    if source != AuthoritativeResultSource.LOCAL_CODE_SCAN.value or not label_id:
        return False
    return not any(
        p.validation_status is ProductLabelOutcomeStatus.VALID for p in product_results
    )


def _legacy_manual_correction(
    *,
    code: str,
    row: AuthoritativeLocalCodeScanResult,
    qty_status: str,
) -> list[ProcessedProductLabel]:
    if qty_status == AuthoritativeQuantityStatus.MISSING.value or row.quantity is None:
        return [
            ProcessedProductLabel(
                label_id=None,
                internal_code=code,
                quantity=0,
                format_version=None,
                checksum=None,
                validation_status=ProductLabelOutcomeStatus.VALID,
                detail="authoritative_manual_correction_legacy_missing_quantity",
            )
        ]
    qty = row.quantity
    if not isinstance(qty, int) or qty <= 0:
        return []
    return [
        ProcessedProductLabel(
            label_id=None,
            internal_code=code,
            quantity=qty,
            format_version=None,
            checksum=None,
            validation_status=ProductLabelOutcomeStatus.VALID,
            detail="authoritative_manual_correction",
        )
    ]


def _legacy_code_scan(
    *,
    code: str,
    row: AuthoritativeLocalCodeScanResult,
    qty_status: str,
) -> list[ProcessedProductLabel]:
    if qty_status == AuthoritativeQuantityStatus.MISSING.value or row.quantity is None:
        return [
            ProcessedProductLabel(
                label_id=None,
                internal_code=code,
                quantity=0,
                format_version=None,
                checksum=None,
                validation_status=ProductLabelOutcomeStatus.VALID,
                detail="legacy_missing_quantity",
            )
        ]
    qty = row.quantity
    if not isinstance(qty, int) or qty <= 0:
        return []
    return [
        ProcessedProductLabel(
            label_id=None,
            internal_code=code,
            quantity=qty,
            format_version=None,
            checksum=None,
            validation_status=ProductLabelOutcomeStatus.VALID,
            detail="authoritative_local_legacy_no_label_id",
        )
    ]


def _d1_code_scan(
    *,
    code: str,
    label_id: str,
    row: AuthoritativeLocalCodeScanResult,
    qty_status: str,
    client_id: str,
    issued_resolver: IssuedProductLabelResolver | None,
) -> list[ProcessedProductLabel]:
    if qty_status == AuthoritativeQuantityStatus.MISSING.value or row.quantity is None:
        return [
            ProcessedProductLabel(
                label_id=label_id,
                internal_code=code,
                quantity=None,
                format_version="D1",
                checksum=None,
                validation_status=ProductLabelOutcomeStatus.QUANTITY_INVALID,
                detail="authoritative_d1_quantity_missing",
            )
        ]

    qty = row.quantity
    if not isinstance(qty, int) or qty <= 0:
        return [
            ProcessedProductLabel(
                label_id=label_id,
                internal_code=code,
                quantity=qty if isinstance(qty, int) else None,
                format_version="D1",
                checksum=None,
                validation_status=ProductLabelOutcomeStatus.QUANTITY_INVALID,
                detail="authoritative_d1_quantity_not_positive",
            )
        ]

    raw = build_product_label_payload(
        label_id=label_id,
        internal_code=code,
        quantity=qty,
    )
    parsed = parse_product_label_payload(raw)
    if parsed.status is not ProductLabelValidationStatus.VALID:
        outcome = _PARSE_STATUS_TO_OUTCOME.get(
            parsed.status, ProductLabelOutcomeStatus.MALFORMED
        )
        return [
            ProcessedProductLabel(
                label_id=label_id,
                internal_code=parsed.internal_code or code,
                quantity=parsed.quantity,
                format_version=parsed.format_version,
                checksum=parsed.checksum_received,
                validation_status=outcome,
                raw_payload=parsed.raw_value,
                normalized_payload=parsed.normalized_payload,
                detail=parsed.detail or "authoritative_d1_parse_failed",
            )
        ]

    if issued_resolver is None:
        return [
            ProcessedProductLabel(
                label_id=label_id,
                internal_code=code,
                quantity=qty,
                format_version="D1",
                checksum=parsed.checksum_received,
                validation_status=ProductLabelOutcomeStatus.CONFIG_ERROR,
                raw_payload=raw,
                normalized_payload=parsed.normalized_payload,
                detail="issued_label_resolver_unavailable",
            )
        ]

    resolved = issued_resolver.resolve_parsed(
        parsed=parsed,
        expected_client_id=client_id,
    )
    if resolved.product is not None:
        return [resolved.product]

    status = resolved.status
    return [
        ProcessedProductLabel(
            label_id=label_id,
            internal_code=code,
            quantity=qty,
            format_version="D1",
            checksum=parsed.checksum_received,
            validation_status=status,
            raw_payload=raw,
            normalized_payload=parsed.normalized_payload,
            detail=resolved.detail or f"issued_resolve_{status.value.lower()}",
        )
    ]
