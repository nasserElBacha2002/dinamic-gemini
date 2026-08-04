"""Strict RFC 4180 parser for local inventory CSV schema version 1.

Formula-like text cells are prefixed with an apostrophe before they enter persistence.
This preserves the text while preventing spreadsheet execution if reports are exported.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime

from src.domain.local_csv_import.entities import LOCAL_CSV_IMPORT_SOURCE

SCHEMA_VERSION = "1"
FORMULA_PREFIXES = ("=", "+", "-", "@")
REQUIRED_HEADERS = (
    "schema_version",
    "export_id",
    "exported_at",
    "device_id",
    "inventory_id",
    "aisle_id",
    "capture_session_id",
    "capture_photo_id",
    "client_file_id",
    "capture_order",
    "captured_at",
    "position_code",
    "internal_code",
    "quantity",
    "quantity_status",
    "detection_status",
    "source",
    "requires_review",
    "error_code",
    "notes",
)
_FORMULA_AWARE_COLUMNS = frozenset(
    {
        "export_id",
        "device_id",
        "inventory_id",
        "aisle_id",
        "capture_session_id",
        "capture_photo_id",
        "client_file_id",
        "position_code",
        "internal_code",
        "source",
        "error_code",
        "notes",
    }
)


class LocalCsvDocumentError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class ParsedLocalCsvRow:
    row_number: int
    values: dict[str, str]
    capture_order: int | None
    exported_at: datetime | None
    captured_at: datetime | None
    quantity: int | None
    requires_review: bool | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ParsedLocalCsv:
    content_hash: str
    export_id: str
    schema_version: str
    inventory_id: str
    device_id: str
    exported_at: datetime
    rows: tuple[ParsedLocalCsvRow, ...]


def _parse_datetime(value: str, field: str, errors: list[str]) -> datetime | None:
    text = value.strip()
    if not text:
        errors.append(f"{field}:required")
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field}:invalid_datetime")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field}:timezone_required")
        return None
    return parsed


def _parse_integer(
    value: str, field: str, errors: list[str], *, optional: bool = False
) -> int | None:
    text = value.strip()
    if optional and not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        errors.append(f"{field}:invalid_integer")
        return None
    if parsed < 0:
        errors.append(f"{field}:must_be_non_negative")
        return None
    return parsed


def _parse_bool(value: str, errors: list[str]) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    errors.append("requires_review:invalid_boolean")
    return None


def _neutralize_formula(value: str) -> tuple[str, bool]:
    stripped = value.lstrip()
    if stripped.startswith(FORMULA_PREFIXES):
        leading = value[: len(value) - len(stripped)]
        return f"{leading}'{stripped}", True
    return value, False


def parse_local_csv(content: bytes) -> ParsedLocalCsv:
    """Parse a complete UTF-8 CSV document using strict RFC 4180 rules."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LocalCsvDocumentError("CSV_INVALID_ENCODING", "CSV must be UTF-8") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = tuple(reader.fieldnames or ())
        missing = [name for name in REQUIRED_HEADERS if name not in headers]
        if missing:
            raise LocalCsvDocumentError(
                "CSV_MISSING_HEADERS", f"Missing required headers: {', '.join(missing)}"
            )
        parsed_rows: list[ParsedLocalCsvRow] = []
        for row_number, raw in enumerate(reader, start=2):
            errors: list[str] = []
            warnings: list[str] = []
            if None in raw:
                errors.append("row:extra_columns")
            values: dict[str, str] = {}
            for name in REQUIRED_HEADERS:
                raw_value = raw.get(name)
                value = "" if raw_value is None else str(raw_value)
                if name in _FORMULA_AWARE_COLUMNS:
                    value, neutralized = _neutralize_formula(value)
                    if neutralized:
                        warnings.append(f"{name}:csv_formula_neutralized")
                values[name] = value.strip()

            for required in (
                "export_id",
                "device_id",
                "inventory_id",
                "aisle_id",
                "capture_session_id",
                "capture_photo_id",
                "client_file_id",
                "position_code",
                "quantity_status",
                "detection_status",
            ):
                if not values[required]:
                    errors.append(f"{required}:required")
            if values["schema_version"] != SCHEMA_VERSION:
                errors.append("schema_version:unsupported")
            if values["source"] != LOCAL_CSV_IMPORT_SOURCE:
                errors.append("source:must_be_LOCAL_CSV_IMPORT")
            exported_at = _parse_datetime(values["exported_at"], "exported_at", errors)
            captured_at = _parse_datetime(values["captured_at"], "captured_at", errors)
            capture_order = _parse_integer(values["capture_order"], "capture_order", errors)
            quantity = _parse_integer(values["quantity"], "quantity", errors, optional=True)
            requires_review = _parse_bool(values["requires_review"], errors)
            parsed_rows.append(
                ParsedLocalCsvRow(
                    row_number=row_number,
                    values=values,
                    capture_order=capture_order,
                    exported_at=exported_at,
                    captured_at=captured_at,
                    quantity=quantity,
                    requires_review=requires_review,
                    errors=tuple(errors),
                    warnings=tuple(warnings),
                )
            )
    except csv.Error as exc:
        raise LocalCsvDocumentError("CSV_MALFORMED", f"Malformed RFC 4180 CSV: {exc}") from exc

    if not parsed_rows:
        raise LocalCsvDocumentError("CSV_EMPTY", "CSV must contain at least one data row")
    first = parsed_rows[0]
    if first.exported_at is None:
        raise LocalCsvDocumentError("CSV_INVALID_METADATA", "First row exported_at is invalid")
    return ParsedLocalCsv(
        content_hash=f"sha256:{hashlib.sha256(content).hexdigest()}",
        export_id=first.values["export_id"],
        schema_version=first.values["schema_version"],
        inventory_id=first.values["inventory_id"],
        device_id=first.values["device_id"],
        exported_at=first.exported_at,
        rows=tuple(parsed_rows),
    )
