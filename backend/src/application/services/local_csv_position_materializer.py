"""Materialize confirmed local CSV/package productive rows into aisle positions.

Writes legacy-scoped ``Position`` + ``ProductRecord`` rows (``job_id=None``) so
``GET .../positions`` shows import results the same way as pre-multi-run / legacy
pipeline results when ``aisles.operational_job_id`` is unset.

When a row carries ``label_id``, the issued-label registry is used to authorize
SKU/qty when possible. If the registry cannot resolve the label, the CSV/device
values are still materialized with ``needs_review=True`` (no silent drop).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime

from src.application.ports.client_position_label_repository import ClientPositionLabelRepository
from src.application.ports.inventory_counted_product_label_repository import (
    InventoryCountedProductLabel,
    InventoryCountedProductLabelRepository,
)
from src.application.ports.repositories import (
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.positioning_label_signing import PositioningLabelSigningService
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.domain.aisle_location.payload import validate_positioning_payload
from src.domain.client_position_label.entities import ClientPositionLabelStatus
from src.domain.local_csv_import.entities import LocalCsvProductiveResult
from src.domain.positions.entities import Position, PositionCreationSource, PositionStatus
from src.domain.product_labels.format import (
    build_product_label_payload,
    parse_product_label_payload,
)
from src.domain.product_labels.processed import ProductLabelOutcomeStatus
from src.domain.products.entities import ProductRecord

# Stable namespace so re-confirm is idempotent without scanning aisle history.
_LOCAL_CSV_POSITION_NS = uuid.UUID("a7e1c4d2-9b3f-4e8a-91d0-6f2c5b8e4a11")

SUMMARY_IMPORT_ROW_ID = "local_csv_import_row_id"
SUMMARY_PRODUCTIVE_ID = "local_csv_productive_result_id"
SUMMARY_INGESTION_SOURCE = "ingestion_source"

# Position-marker photos are capture context, not inventory line items.
_POSITION_MARKER_SOURCES = frozenset({"LOCAL_POSITION_LABEL"})

logger = logging.getLogger(__name__)


def is_inventory_line_result(result: LocalCsvProductiveResult) -> bool:
    """True when the productive row should appear in aisle results as a counted item."""
    source = (result.detection_source or "").strip().upper()
    if source in _POSITION_MARKER_SOURCES:
        return False
    return True


def position_id_for_productive(productive_id: str) -> str:
    return str(uuid.uuid5(_LOCAL_CSV_POSITION_NS, f"local-csv-pos:{productive_id}"))


def product_id_for_productive(productive_id: str) -> str:
    return str(uuid.uuid5(_LOCAL_CSV_POSITION_NS, f"local-csv-prod:{productive_id}"))


def _sku_for(result: LocalCsvProductiveResult) -> str:
    code = (result.internal_code or "").strip()
    return code if code else "UNKNOWN"


def _quantity_for(result: LocalCsvProductiveResult) -> int:
    if result.quantity is None:
        return 0
    try:
        return max(0, int(result.quantity))
    except (TypeError, ValueError):
        return 0


def _qty_parse_status(qty: int, raw_quantity: int | None) -> str:
    if raw_quantity is None:
        return "missing"
    if qty <= 0:
        return "zero"
    return "valid_positive"


def _detected_summary(
    result: LocalCsvProductiveResult,
    *,
    label_registry_status: str | None = None,
    label_authority: str | None = None,
) -> dict:
    position_code = (result.position_code or "").strip() or None
    internal = (result.internal_code or "").strip() or None
    qty = _quantity_for(result)
    summary: dict = {
        SUMMARY_IMPORT_ROW_ID: result.import_row_id,
        SUMMARY_PRODUCTIVE_ID: result.id,
        SUMMARY_INGESTION_SOURCE: result.ingestion_source,
        "detection_status": result.detection_status,
        "detection_source": result.detection_source,
        "quantity_status": result.quantity_status,
        "capture_session_id": result.capture_session_id,
        "capture_photo_id": result.capture_photo_id,
        "client_file_id": result.client_file_id,
        "entity_type": "PALLET",
        "entity_uid": f"local_csv:{result.id}",
        "final_quantity": qty,
    }
    if internal:
        summary["internal_code"] = internal
        summary["review_display_label"] = internal
    if position_code:
        summary["position_barcode"] = position_code
        summary["pallet_id"] = position_code
        if not internal:
            summary["review_display_label"] = position_code
    if result.source_asset_id:
        summary["source_image_id"] = result.source_asset_id
        summary["source_asset_id"] = result.source_asset_id
        # Domain TraceabilityStatus.VALID — required for evidence display (Phase 4.8).
        summary["traceability_status"] = "valid"
        summary["has_valid_evidence"] = True
    if result.capture_order is not None:
        summary["source_image_sequence"] = result.capture_order
    label_id = (result.label_id or "").strip().upper() or None
    if label_id:
        summary["label_id"] = label_id
    position_label_id = (result.position_label_id or "").strip() or None
    if position_label_id:
        summary["position_label_id"] = position_label_id
    if label_registry_status:
        summary["label_registry_status"] = label_registry_status
    if label_authority:
        summary["label_authority"] = label_authority
    return summary


class LocalCsvPositionMaterializer:
    """Persist aisle-visible Position/ProductRecord rows from productive CSV results."""

    def __init__(
        self,
        *,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        counted_product_label_repo: InventoryCountedProductLabelRepository,
        issued_label_resolver: IssuedProductLabelResolver,
        inventory_repo: InventoryRepository | None = None,
        client_position_label_repo: ClientPositionLabelRepository | None = None,
        positioning_signing: PositioningLabelSigningService | None = None,
    ) -> None:
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._counted_product_label_repo = counted_product_label_repo
        self._issued_label_resolver = issued_label_resolver
        self._inventory_repo = inventory_repo
        self._client_position_label_repo = client_position_label_repo
        self._positioning_signing = positioning_signing

    def materialize(
        self,
        results: Sequence[LocalCsvProductiveResult],
        *,
        now: datetime,
        inventory_client_id: str | None = None,
    ) -> int:
        """Create or refresh inventory line positions. Returns rows written.

        ``LOCAL_POSITION_LABEL`` (and similar markers) are skipped — they only
        supply ``position_code`` for later product rows and must not appear as items.
        Previously materialized marker rows are retired (status=deleted).
        """
        written = 0
        for result in results:
            if not is_inventory_line_result(result):
                self._retire_marker_row(result, now=now)
                continue
            if self._materialize_one(
                result, now=now, inventory_client_id=inventory_client_id
            ):
                written += 1
        return written

    def _resolve_inventory_client_id(
        self,
        result: LocalCsvProductiveResult,
        inventory_client_id: str | None,
    ) -> str | None:
        explicit = (inventory_client_id or "").strip() or None
        if explicit:
            return explicit
        if self._inventory_repo is None:
            return None
        inventory = self._inventory_repo.get_by_id(result.inventory_id)
        if inventory is None:
            return None
        return (inventory.client_id or "").strip() or None

    def _retire_marker_row(self, result: LocalCsvProductiveResult, *, now: datetime) -> None:
        position_id = position_id_for_productive(result.id)
        existing = self._position_repo.get_by_id(position_id)
        if existing is None:
            return
        if existing.status == PositionStatus.DELETED:
            return
        retired = Position(
            id=existing.id,
            aisle_id=existing.aisle_id,
            status=PositionStatus.DELETED,
            confidence=existing.confidence,
            needs_review=False,
            primary_evidence_id=existing.primary_evidence_id,
            created_at=existing.created_at,
            updated_at=now,
            review_resolution=existing.review_resolution,
            detected_summary_json=existing.detected_summary_json,
            corrected_summary_json=existing.corrected_summary_json,
            corrected_position_code=existing.corrected_position_code,
            job_id=existing.job_id,
            creation_source=existing.creation_source,
        )
        self._position_repo.save(retired)

    def _validate_position_payload(
        self,
        result: LocalCsvProductiveResult,
        *,
        inventory_client_id: str | None,
    ) -> bool:
        """Validate optional positioning payload; fail-closed on invalid structure/HMAC/registry."""
        raw = (result.position_payload_raw or "").strip()
        if not raw:
            return True
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning(
                "local_csv_position_payload_invalid productive_id=%s reason=json",
                result.id,
            )
            return False
        try:
            validate_positioning_payload(payload)
        except ValueError as exc:
            logger.warning(
                "local_csv_position_payload_invalid productive_id=%s reason=%s",
                result.id,
                exc,
            )
            return False
        signing = self._positioning_signing
        if signing is not None and signing.can_sign:
            if not signing.verify_payload(payload):
                logger.warning(
                    "local_csv_position_payload_hmac_failed productive_id=%s",
                    result.id,
                )
                return False
        if self._client_position_label_repo is None:
            return True
        public_id = str(payload.get("label_id") or "").strip()
        label = self._client_position_label_repo.get_by_public_identifier(public_id)
        if label is None and (result.position_label_id or "").strip():
            label = self._client_position_label_repo.get_by_id(
                (result.position_label_id or "").strip()
            )
        if label is None:
            logger.warning(
                "local_csv_position_label_unknown productive_id=%s public_id=%s",
                result.id,
                public_id,
            )
            return False
        if label.status != ClientPositionLabelStatus.ACTIVE:
            logger.warning(
                "local_csv_position_label_inactive productive_id=%s label_id=%s",
                result.id,
                label.id,
            )
            return False
        client_id = self._resolve_inventory_client_id(result, inventory_client_id)
        if client_id and (label.client_id or "").strip() != client_id:
            logger.warning(
                "local_csv_position_label_client_mismatch productive_id=%s",
                result.id,
            )
            return False
        return True

    def _resolve_issued_label(
        self,
        result: LocalCsvProductiveResult,
        *,
        label_id: str,
        inventory_client_id: str | None,
    ) -> tuple[str, int] | None:
        """Return authoritative (sku, qty) when issued registry accepts the row; else None."""
        client_id = self._resolve_inventory_client_id(result, inventory_client_id)
        if not client_id:
            logger.warning(
                "local_csv_label_missing_client productive_id=%s label_id=%s",
                result.id,
                label_id,
            )
            return None
        sku = _sku_for(result)
        qty = _quantity_for(result)
        if sku == "UNKNOWN" or qty < 1:
            logger.warning(
                "local_csv_label_fields_invalid productive_id=%s label_id=%s",
                result.id,
                label_id,
            )
            return None
        try:
            raw = build_product_label_payload(
                label_id=label_id, internal_code=sku, quantity=qty
            )
        except ValueError as exc:
            logger.warning(
                "local_csv_label_payload_build_failed productive_id=%s detail=%s",
                result.id,
                exc,
            )
            return None
        parsed = parse_product_label_payload(raw)
        resolved = self._issued_label_resolver.resolve_parsed(
            parsed=parsed, expected_client_id=client_id
        )
        if resolved.status is not ProductLabelOutcomeStatus.VALID or resolved.product is None:
            logger.warning(
                "local_csv_label_resolve_rejected productive_id=%s label_id=%s status=%s",
                result.id,
                label_id,
                resolved.status.value,
            )
            return None
        auth_sku = (resolved.product.internal_code or "").strip() or sku
        auth_qty = (
            int(resolved.product.quantity)
            if resolved.product.quantity is not None
            else qty
        )
        return auth_sku, auth_qty

    def _materialize_one(
        self,
        result: LocalCsvProductiveResult,
        *,
        now: datetime,
        inventory_client_id: str | None = None,
    ) -> bool:
        # Invalid positioning payloads must not hide inventory lines from package/CSV
        # imports. Skip enrichment and still materialize the counted row.
        position_payload_ok = self._validate_position_payload(
            result, inventory_client_id=inventory_client_id
        )
        if not position_payload_ok:
            logger.warning(
                "local_csv_position_payload_ignored_for_materialize productive_id=%s",
                result.id,
            )

        position_id = position_id_for_productive(result.id)
        product_id = product_id_for_productive(result.id)
        position_code = (result.position_code or "").strip() or None
        sku = _sku_for(result)
        qty = _quantity_for(result)
        needs_review = bool(result.requires_review) or sku == "UNKNOWN" or result.quantity is None
        label_id = (result.label_id or "").strip().upper() or None
        label_registry_status: str | None = None
        label_authority: str | None = None

        existing = self._position_repo.get_by_id(position_id)
        created_at = existing.created_at if existing is not None else now

        save_product = True
        if label_id:
            resolved = self._resolve_issued_label(
                result, label_id=label_id, inventory_client_id=inventory_client_id
            )
            if resolved is None:
                # Generic handoff path: device/CSV values remain visible even when the
                # issued-label registry cannot authorize the label_id yet.
                label_registry_status = "unresolved"
                label_authority = "csv_fallback"
                needs_review = True
                logger.warning(
                    "local_csv_label_unresolved_fallback productive_id=%s label_id=%s "
                    "sku=%s qty=%s",
                    result.id,
                    label_id,
                    sku,
                    qty,
                )
            else:
                sku, qty = resolved
                needs_review = bool(result.requires_review)
                label_registry_status = "ok"
                label_authority = "issued"
                claimed = self._counted_product_label_repo.try_claim(
                    InventoryCountedProductLabel(
                        id=str(uuid.uuid4()),
                        inventory_id=result.inventory_id,
                        aisle_id=result.aisle_id,
                        label_id=label_id,
                        first_product_record_id=product_id,
                        first_source_asset_id=(result.source_asset_id or "").strip()
                        or position_id,
                        first_job_id="",
                        first_position_id=position_id,
                        created_at=now,
                    )
                )
                if not claimed:
                    # Idempotent re-import / cross-row dedupe: never create a second ProductRecord.
                    # Still refresh position when it already exists from the winning claim path.
                    if existing is None:
                        return False
                    save_product = False

        # Link the package photo as primary evidence so list ``has_evidence`` is true
        # (canonical view keys has_evidence off primary_evidence_id).
        evidence_asset_id = (result.source_asset_id or "").strip() or None

        summary = _detected_summary(
            result,
            label_registry_status=label_registry_status,
            label_authority=label_authority,
        )
        if not position_payload_ok:
            summary["position_payload_status"] = "ignored_invalid"

        position = Position(
            id=position_id,
            aisle_id=result.aisle_id,
            status=PositionStatus.DETECTED,
            confidence=1.0,
            needs_review=needs_review,
            primary_evidence_id=evidence_asset_id,
            created_at=created_at,
            updated_at=now,
            review_resolution=None,
            detected_summary_json=summary,
            corrected_summary_json=None,
            corrected_position_code=position_code,
            job_id=None,
            creation_source=PositionCreationSource.AUTOMATIC,
        )
        self._position_repo.save(position)

        if save_product:
            product = ProductRecord(
                id=product_id,
                position_id=position_id,
                sku=sku,
                description=None,
                detected_quantity=qty,
                corrected_quantity=None,
                confidence=1.0,
                created_at=created_at,
                updated_at=now,
                qty_source="local_csv_import",
                qty_inference_reason=None,
                raw_qty=result.quantity,
                qty_parse_status=_qty_parse_status(qty, result.quantity),
                label_id=label_id,
            )
            self._product_record_repo.save(product)
        return True
