"""Strict RFC 4180 parser for local inventory CSV schema version 1.

Formula-like text cells are prefixed with an apostrophe before they enter persistence.
Detection provenance stays in CSV column `source`; the server assigns ingestion_source.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime

from src.domain.local_csv_import.sources import (
    ALLOWED_DETECTION_SOURCES,
    INGESTION_SOURCE_LOCAL_CSV_IMPORT,
    LEGACY_SOURCE_AS_DETECTION,
)
from src.domain.product_labels.format import LABEL_ID_ALPHABET, LABEL_ID_LENGTH

SCHEMA_VERSION = "1"
SCHEMA_VERSION_WITH_LABEL_ID = "1.1"
SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION, SCHEMA_VERSION_WITH_LABEL_ID})
FORMULA_PREFIXES = ("=", "+", "-", "@")

# Headers required by the mobile exporter contract (extra headers are ignored).
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

# Optional in v1; required presence-as-column for schema 1.1 exporters (still optional value).
OPTIONAL_HEADERS = ("label_id", "position_label_id", "position_payload_raw")
_LABEL_ID_ALLOWED = frozenset(LABEL_ID_ALPHABET)

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
        "label_id",
        "position_label_id",
        "position_payload_raw",
        "source",
        "error_code",
        "notes",
    }
)


def _normalize_optional_label_id(raw: str, errors: list[str]) -> str:
    """Return uppercase label_id, empty string for legacy, or record format error."""
    text = (raw or "").strip()
    if not text:
        return ""
    normalized = text.upper()
    if len(normalized) != LABEL_ID_LENGTH or any(ch not in _LABEL_ID_ALLOWED for ch in normalized):
        errors.append("label_id:invalid_format")
        return normalized
    return normalized


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
    detection_source: str
    ingestion_source: str
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


def _normalize_detection_source(raw: str, errors: list[str], warnings: list[str]) -> str:
    value = raw.strip()
    if not value:
        errors.append("source:required")
        return ""
    if value in ALLOWED_DETECTION_SOURCES:
        return value
    if value in LEGACY_SOURCE_AS_DETECTION:
        warnings.append("source:legacy_LOCAL_CSV_IMPORT_treated_as_LOCAL_PENDING")
        return "LOCAL_PENDING"
    errors.append("source:unsupported_detection_source")
    return value


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
        has_label_id_header = "label_id" in headers
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

            schema_version = values["schema_version"]
            if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
                errors.append("schema_version:unsupported")
            if schema_version == SCHEMA_VERSION_WITH_LABEL_ID and not has_label_id_header:
                errors.append("label_id:header_required")
            # Copy optional label_id when the column is present; never invent IDs.
            if has_label_id_header:
                raw_label = raw.get("label_id")
                label_value = "" if raw_label is None else str(raw_label)
                if "label_id" in _FORMULA_AWARE_COLUMNS:
                    label_value, neutralized = _neutralize_formula(label_value)
                    if neutralized:
                        warnings.append("label_id:csv_formula_neutralized")
                values["label_id"] = _normalize_optional_label_id(label_value, errors)

            for optional_name in ("position_label_id", "position_payload_raw"):
                if optional_name not in headers:
                    continue
                raw_opt = raw.get(optional_name)
                opt_value = "" if raw_opt is None else str(raw_opt)
                if optional_name in _FORMULA_AWARE_COLUMNS:
                    opt_value, neutralized = _neutralize_formula(opt_value)
                    if neutralized:
                        warnings.append(f"{optional_name}:csv_formula_neutralized")
                values[optional_name] = opt_value.strip()

            for required in (
                "export_id",
                "device_id",
                "inventory_id",
                "aisle_id",
                "capture_session_id",
                "capture_photo_id",
                "quantity_status",
                "detection_status",
            ):
                if not values[required]:
                    errors.append(f"{required}:required")
            # position_code may be empty → requires review later
            if not values["position_code"]:
                warnings.append("position_code:empty")
            if not values["client_file_id"]:
                values["client_file_id"] = values["capture_photo_id"]
                warnings.append("client_file_id:defaulted_to_capture_photo_id")
            detection_source = _normalize_detection_source(values["source"], errors, warnings)
            exported_at = _parse_datetime(values["exported_at"], "exported_at", errors)
            captured_at = _parse_datetime(values["captured_at"], "captured_at", errors)
            capture_order = _parse_integer(values["capture_order"], "capture_order", errors)
            quantity = _parse_integer(values["quantity"], "quantity", errors, optional=True)
            requires_review = _parse_bool(values["requires_review"], errors)
            if requires_review is False and not values["position_code"]:
                requires_review = True
                warnings.append("requires_review:forced_for_empty_position")
            parsed_rows.append(
                ParsedLocalCsvRow(
                    row_number=row_number,
                    values=values,
                    capture_order=capture_order,
                    exported_at=exported_at,
                    captured_at=captured_at,
                    quantity=quantity,
                    requires_review=requires_review,
                    detection_source=detection_source,
                    ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
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
