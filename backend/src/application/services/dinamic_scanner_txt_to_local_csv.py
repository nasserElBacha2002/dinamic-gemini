"""Convert parsed Dinamic Scanner TXT into the local CSV import pipeline shape."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from src.application.services.dinamic_scanner_txt_parser import (
    ParsedDinamicScannerTxt,
    ParsedScannerProduct,
)
from src.application.services.local_csv_parser import (
    SCHEMA_VERSION_WITH_LABEL_ID,
    ParsedLocalCsv,
    ParsedLocalCsvRow,
)
from src.domain.aisle_location.payload import build_positioning_label_payload
from src.domain.client_position_label.hierarchy import PositionSide
from src.domain.dinamic_scanner_txt.constants import SCANNER_TXT_DEVICE_ID
from src.domain.dinamic_scanner_txt.errors import TXT_EMPTY, DinamicScannerTxtImportError
from src.domain.local_csv_import.sources import (
    INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
    LOCAL_CODE_SCAN_DETECTION_SOURCE,
)


def _position_payload_raw(product: ParsedScannerProduct) -> tuple[str, tuple[str, ...]]:
    position = product.position
    if position is None:
        return "", ()
    side = PositionSide(position.side.strip().upper())
    payload = build_positioning_label_payload(
        public_label_id=position.label_id,
        pallet=position.pallet,
        side=side,
        level=1,
        marker_index=1,
        marker_total=1,
    )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False), ()


def _export_id(content_hash: str, aisle_code: str, inventory_id: str) -> str:
    digest = hashlib.sha256(f"{content_hash}|{inventory_id}|{aisle_code}".encode()).hexdigest()
    return f"scanner-txt-{digest[:24]}"


def _scan_row_ref(export_id: str, row_number: int) -> str:
    """Stable scan-row reference (not a photo id; required by CSV pipeline NOT NULL columns)."""
    return f"txt-scan-{export_id}-line-{row_number}"


def build_parsed_local_csv_from_scanner_txt(
    *,
    parsed_txt: ParsedDinamicScannerTxt,
    inventory_id: str,
    aisle_id: str,
    aisle_code: str,
    exported_at: datetime,
    device_id: str = SCANNER_TXT_DEVICE_ID,
) -> ParsedLocalCsv:
    """Map scanner products to ParsedLocalCsv rows for PreviewLocalCsvImport."""
    if not parsed_txt.products:
        raise DinamicScannerTxtImportError(
            TXT_EMPTY, "TXT contains no product (D1) records"
        )

    export_id = _export_id(parsed_txt.content_hash, aisle_code, inventory_id)
    session_id = f"scanner-txt-{export_id}"
    exported_at_text = exported_at.isoformat().replace("+00:00", "Z")
    rows: list[ParsedLocalCsvRow] = []

    for index, product in enumerate(parsed_txt.products, start=1):
        position = product.position
        position_code = position.pallet if position is not None else ""
        position_label_id = position.label_id if position is not None else ""
        position_payload_raw, payload_errors = _position_payload_raw(product)
        errors = tuple(dict.fromkeys((*product.errors, *payload_errors)))
        scan_ref = _scan_row_ref(export_id, product.line_number)
        values = {
            "schema_version": SCHEMA_VERSION_WITH_LABEL_ID,
            "export_id": export_id,
            "exported_at": exported_at_text,
            "device_id": device_id,
            "inventory_id": inventory_id,
            "aisle_id": aisle_id,
            "capture_session_id": session_id,
            "capture_photo_id": scan_ref,
            "client_file_id": scan_ref,
            "capture_order": str(index),
            "captured_at": exported_at_text,
            "position_code": position_code,
            "internal_code": product.internal_code,
            "quantity": "" if product.quantity is None else str(product.quantity),
            "quantity_status": "PRESENT",
            "detection_status": "DETECTED",
            "source": LOCAL_CODE_SCAN_DETECTION_SOURCE,
            "requires_review": "false",
            "error_code": "",
            "notes": "dinamic-scanner-txt",
            "label_id": product.label_id,
            "position_label_id": position_label_id,
            "position_payload_raw": position_payload_raw,
        }
        requires_review = not bool(position_code)
        if requires_review:
            values["requires_review"] = "true"
        rows.append(
            ParsedLocalCsvRow(
                row_number=product.line_number,
                values=values,
                capture_order=index,
                exported_at=exported_at,
                captured_at=exported_at,
                quantity=product.quantity,
                requires_review=requires_review,
                detection_source=LOCAL_CODE_SCAN_DETECTION_SOURCE,
                ingestion_source=INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
                errors=errors,
                warnings=product.warnings,
            )
        )

    return ParsedLocalCsv(
        content_hash=parsed_txt.content_hash,
        export_id=export_id,
        schema_version=SCHEMA_VERSION_WITH_LABEL_ID,
        inventory_id=inventory_id,
        device_id=device_id,
        exported_at=exported_at,
        rows=tuple(rows),
    )
