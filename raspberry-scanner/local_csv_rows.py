"""Build ``results.csv`` rows from durable Raspberry capture session state."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from capture_session_store import CaptureSessionState, PhotoCaptureRecord
from local_package_contract import LOCAL_CSV_HEADERS, LOCAL_CSV_SCHEMA_VERSION
from scan_semantics import (
    ScanSemantics,
    position_from_snapshot,
    products_from_snapshot,
    semantics_for_photo,
)

_FORMULA_PREFIX = re.compile(r"^[=+\-@\t\r]")


@dataclass(frozen=True)
class LocalCsvBuildResult:
    export_id: str
    exported_at: str
    csv_text: str
    csv_checksum_sha256: str
    row_count: int
    product_result_count: int
    position_event_count: int
    rejected_detection_count: int
    rows: tuple[dict[str, str], ...]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _neutralize_csv_formula(value: str) -> str:
    if not value:
        return value
    if _FORMULA_PREFIX.match(value):
        return f"'{value}"
    return value


def _escape_csv_field(raw: str) -> str:
    value = _neutralize_csv_formula(raw)
    if any(ch in value for ch in '",\n\r'):
        return '"' + value.replace('"', '""') + '"'
    return value


def build_csv_document(rows: list[dict[str, str]]) -> str:
    lines = [",".join(LOCAL_CSV_HEADERS)]
    for row in rows:
        lines.append(",".join(_escape_csv_field(row[h]) for h in LOCAL_CSV_HEADERS))
    return "\n".join(lines) + "\n"


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_position_export_line(line: str) -> tuple[str, str, str, str]:
    parts = line.split("|")
    if len(parts) < 4 or parts[0] != "POSITION":
        return "", "", "", ""
    label_id = parts[1].strip()
    pallet = parts[2].strip()
    side = parts[3].strip().upper()
    position_code = label_id or pallet
    return position_code, label_id, side, line


def _running_position_from_photos(
    photos: list[PhotoCaptureRecord],
    up_to_sequence: int,
) -> tuple[str, str, str]:
    position_code = ""
    position_label_id = ""
    position_payload_raw = ""
    for photo in sorted(photos, key=lambda p: p.sequence_number):
        if photo.sequence_number > up_to_sequence:
            break
        semantics = semantics_for_photo(photo)
        if semantics.classification == "POSITION":
            supplier = position_from_snapshot(
                semantics.recognition_snapshot_json,
                raw_payload=semantics.raw_payload,
            )
            if supplier:
                position_code = supplier["position_code"]
                position_label_id = supplier["position_label_id"]
                position_payload_raw = supplier["position_payload_raw"]
                continue
        if semantics.export_line.startswith("POSITION|"):
            position_code, position_label_id, _side, position_payload_raw = (
                _parse_position_export_line(semantics.export_line)
            )
    return position_code, position_label_id, position_payload_raw


def _products_for_semantics(semantics: ScanSemantics) -> list[dict[str, object]]:
    if semantics.classification == "RAW" and semantics.selection_mode == "ALL":
        raw = semantics.raw_payload
        return [{"label_id": "", "internal_code": raw, "quantity": None}]
    from_snapshot = products_from_snapshot(semantics.recognition_snapshot_json)
    if from_snapshot:
        return from_snapshot
    if semantics.classification != "ITEM":
        return []
    from src.domain.product_labels.format import (
        ProductLabelValidationStatus,
        parse_product_label_payload,
    )

    parsed = parse_product_label_payload(semantics.export_line)
    if parsed.status != ProductLabelValidationStatus.VALID:
        return []
    label_id = (parsed.label_id or "").strip()
    return [
        {
            "label_id": label_id,
            "internal_code": parsed.internal_code or "",
            "quantity": parsed.quantity,
        }
    ]


def _is_position_photo(semantics: ScanSemantics) -> bool:
    if semantics.classification == "POSITION":
        return True
    if semantics.export_line.startswith("POSITION|"):
        return True
    return (
        position_from_snapshot(
            semantics.recognition_snapshot_json,
            raw_payload=semantics.raw_payload,
        )
        is not None
    )


def build_local_csv_rows(
    session: CaptureSessionState,
    *,
    complete_photos: list[PhotoCaptureRecord],
    inventory_id: str,
    aisle_id: str,
    device_id: str,
    export_id: str | None = None,
    exported_at: str | None = None,
) -> LocalCsvBuildResult:
    export_id_value = export_id or str(uuid.uuid4())
    exported_at_value = exported_at or _utc_now_iso()
    sorted_photos = sorted(complete_photos, key=lambda p: p.sequence_number)
    rows: list[dict[str, str]] = []
    emitted_label_ids: set[str] = set()
    running_position: tuple[str, str, str] | None = None

    for photo in sorted_photos:
        semantics = semantics_for_photo(photo)
        if _is_position_photo(semantics):
            supplier = position_from_snapshot(
                semantics.recognition_snapshot_json,
                raw_payload=semantics.raw_payload,
            )
            if supplier:
                running_position = (
                    supplier["position_code"],
                    supplier["position_label_id"],
                    supplier["position_payload_raw"],
                )
            elif semantics.export_line.startswith("POSITION|"):
                pos_code, pos_label, _side, payload = _parse_position_export_line(
                    semantics.export_line
                )
                running_position = (pos_code, pos_label, payload)

        if running_position:
            position_code, position_label_id, position_payload_raw = running_position
        else:
            position_code, position_label_id, position_payload_raw = (
                _running_position_from_photos(sorted_photos, photo.sequence_number)
            )

        base = {
            "schema_version": LOCAL_CSV_SCHEMA_VERSION,
            "export_id": export_id_value,
            "exported_at": exported_at_value,
            "device_id": device_id,
            "inventory_id": inventory_id,
            "aisle_id": aisle_id,
            "capture_session_id": session.capture_session_id,
            "capture_photo_id": photo.capture_photo_id,
            "client_file_id": photo.capture_photo_id,
            "capture_order": str(photo.sequence_number),
            "captured_at": photo.captured_at,
            "position_code": position_code,
            "position_label_id": position_label_id,
            "position_payload_raw": position_payload_raw,
            "internal_code": "",
            "label_id": "",
            "quantity": "",
            "quantity_status": "",
            "detection_status": "RESOLVED",
            "source": "",
            "requires_review": "false",
            "error_code": "",
            "notes": "",
        }

        if _is_position_photo(semantics) and not _products_for_semantics(semantics):
            pos_code = position_code
            pos_label = position_label_id
            payload = position_payload_raw
            if semantics.export_line.startswith("POSITION|"):
                pos_code, pos_label, _side, payload = _parse_position_export_line(
                    semantics.export_line
                )
            rows.append(
                {
                    **base,
                    "position_code": pos_code,
                    "position_label_id": pos_label,
                    "position_payload_raw": payload,
                    "quantity_status": "NOT_APPLICABLE",
                    "source": "LOCAL_POSITION_LABEL",
                }
            )
            continue

        products = _products_for_semantics(semantics)
        filtered: list[dict[str, object]] = []
        duplicate_only = False
        for product in products:
            label_id = str(product.get("label_id") or "").strip()
            if label_id and label_id in emitted_label_ids:
                duplicate_only = True
                continue
            if label_id:
                emitted_label_ids.add(label_id)
            filtered.append(product)

        if not filtered:
            if duplicate_only and semantics.classification == "ITEM":
                continue
            if _is_position_photo(semantics):
                rows.append(
                    {
                        **base,
                        "quantity_status": "NOT_APPLICABLE",
                        "source": "LOCAL_POSITION_LABEL",
                    }
                )
            continue

        for product in filtered:
            label_id = str(product.get("label_id") or "").strip()
            internal_code = str(product.get("internal_code") or "").strip()
            quantity = product.get("quantity")
            rows.append(
                {
                    **base,
                    "internal_code": internal_code,
                    "label_id": label_id,
                    "quantity": str(quantity) if quantity is not None else "",
                    "quantity_status": "PRESENT" if quantity is not None else "PRESENT",
                    "source": "LOCAL_CODE_SCAN",
                }
            )

    if not rows:
        raise ValueError("PACKAGE_EXPORT_EMPTY")
    product_rows = [
        r
        for r in rows
        if r["source"] == "LOCAL_CODE_SCAN"
        and (r["internal_code"].strip() or r["label_id"].strip())
    ]
    if not product_rows:
        raise ValueError("PACKAGE_EXPORT_NO_PRODUCTS")

    csv_text = build_csv_document(rows)
    return LocalCsvBuildResult(
        export_id=export_id_value,
        exported_at=exported_at_value,
        csv_text=csv_text,
        csv_checksum_sha256=_sha256_hex(csv_text),
        row_count=len(rows),
        product_result_count=sum(1 for r in rows if r["source"] == "LOCAL_CODE_SCAN"),
        position_event_count=sum(
            1 for r in rows if r["source"] == "LOCAL_POSITION_LABEL"
        ),
        rejected_detection_count=0,
        rows=tuple(rows),
    )
