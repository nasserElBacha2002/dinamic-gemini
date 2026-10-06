"""Build ``results.csv`` rows from durable Raspberry capture session state."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from capture_session_store import CaptureSessionState, PhotoCaptureRecord
from local_package_contract import LOCAL_CSV_HEADERS, LOCAL_CSV_SCHEMA_VERSION

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


def _running_position_from_records(
    export_records: list[tuple[int, str]],
    up_to_sequence: int,
) -> tuple[str, str, str]:
    position_code = ""
    position_label_id = ""
    position_payload_raw = ""
    for seq, line in export_records:
        if seq > up_to_sequence:
            break
        if line.startswith("POSITION|"):
            position_code, position_label_id, _side, position_payload_raw = (
                _parse_position_export_line(line)
            )
    return position_code, position_label_id, position_payload_raw


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
    from src.domain.product_labels.format import (
        ProductLabelValidationStatus,
        parse_product_label_payload,
    )

    export_id_value = export_id or str(uuid.uuid4())
    exported_at_value = exported_at or _utc_now_iso()
    sorted_photos = sorted(complete_photos, key=lambda p: p.sequence_number)
    rows: list[dict[str, str]] = []
    emitted_label_ids: set[str] = set()

    for photo in sorted_photos:
        position_code, position_label_id, position_payload_raw = (
            _running_position_from_records(
                session.export_records,
                photo.scanner_sequence,
            )
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
        line = photo.export_line
        if line.startswith("POSITION|"):
            pos_code, pos_label, _side, payload = _parse_position_export_line(line)
            row = {
                **base,
                "position_code": pos_code,
                "position_label_id": pos_label,
                "position_payload_raw": payload,
                "quantity_status": "NOT_APPLICABLE",
                "source": "LOCAL_POSITION_LABEL",
            }
            rows.append(row)
            continue

        parsed = parse_product_label_payload(line)
        if parsed.status != ProductLabelValidationStatus.VALID:
            raise ValueError(f"invalid_product_export_line: {line}")
        label_id = (parsed.label_id or "").strip()
        if label_id and label_id in emitted_label_ids:
            row = {
                **base,
                "quantity_status": "NOT_APPLICABLE",
                "source": "LOCAL_POSITION_LABEL",
            }
            rows.append(row)
            continue
        if label_id:
            emitted_label_ids.add(label_id)
        row = {
            **base,
            "internal_code": parsed.internal_code or "",
            "label_id": label_id,
            "quantity": str(parsed.quantity or ""),
            "quantity_status": "PRESENT",
            "source": "LOCAL_CODE_SCAN",
        }
        rows.append(row)

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
