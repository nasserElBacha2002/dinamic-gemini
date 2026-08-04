"""Materialize confirmed local CSV/package productive rows into aisle positions.

Writes legacy-scoped ``Position`` + ``ProductRecord`` rows (``job_id=None``) so
``GET .../positions`` shows import results the same way as pre-multi-run / legacy
pipeline results when ``aisles.operational_job_id`` is unset.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from src.application.ports.repositories import PositionRepository, ProductRecordRepository
from src.domain.local_csv_import.entities import LocalCsvProductiveResult
from src.domain.positions.entities import Position, PositionCreationSource, PositionStatus
from src.domain.products.entities import ProductRecord

# Stable namespace so re-confirm is idempotent without scanning aisle history.
_LOCAL_CSV_POSITION_NS = uuid.UUID("a7e1c4d2-9b3f-4e8a-91d0-6f2c5b8e4a11")

SUMMARY_IMPORT_ROW_ID = "local_csv_import_row_id"
SUMMARY_PRODUCTIVE_ID = "local_csv_productive_result_id"
SUMMARY_INGESTION_SOURCE = "ingestion_source"

# Position-marker photos are capture context, not inventory line items.
_POSITION_MARKER_SOURCES = frozenset({"LOCAL_POSITION_LABEL"})


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


def _detected_summary(result: LocalCsvProductiveResult) -> dict:
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
    return summary


class LocalCsvPositionMaterializer:
    """Persist aisle-visible Position/ProductRecord rows from productive CSV results."""

    def __init__(
        self,
        *,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
    ) -> None:
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo

    def materialize(
        self,
        results: Sequence[LocalCsvProductiveResult],
        *,
        now: datetime,
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
            self._materialize_one(result, now=now)
            written += 1
        return written

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

    def _materialize_one(self, result: LocalCsvProductiveResult, *, now: datetime) -> None:
        position_id = position_id_for_productive(result.id)
        product_id = product_id_for_productive(result.id)
        position_code = (result.position_code or "").strip() or None
        sku = _sku_for(result)
        qty = _quantity_for(result)
        needs_review = bool(result.requires_review) or sku == "UNKNOWN" or result.quantity is None

        existing = self._position_repo.get_by_id(position_id)
        created_at = existing.created_at if existing is not None else now

        position = Position(
            id=position_id,
            aisle_id=result.aisle_id,
            status=PositionStatus.DETECTED,
            confidence=1.0,
            needs_review=needs_review,
            primary_evidence_id=None,
            created_at=created_at,
            updated_at=now,
            review_resolution=None,
            detected_summary_json=_detected_summary(result),
            corrected_summary_json=None,
            corrected_position_code=position_code,
            job_id=None,
            creation_source=PositionCreationSource.AUTOMATIC,
        )
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
        )
        self._position_repo.save(position)
        self._product_record_repo.save(product)
