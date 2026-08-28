"""Parse Dinamic Scanner ESP32 aisle TXT exports (POSITION + D1 records)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from src.domain.client_position_label.hierarchy import PositionSide
from src.domain.dinamic_scanner_txt.errors import (
    TXT_EMPTY,
    TXT_EMPTY_AISLE_NAME,
    TXT_FILENAME_REQUIRED,
    TXT_INVALID_ENCODING,
    TXT_INVALID_EXTENSION,
    TXT_INVALID_FILENAME,
    TXT_LINE_TOO_LONG,
    TXT_TOO_MANY_LINES,
    DinamicScannerTxtImportError,
)
from src.domain.product_labels.format import (
    ProductLabelValidationStatus,
    parse_product_label_payload,
)

_POSITION_PREFIX = "POSITION|"
_VERSIONED_PRODUCT_PATTERN = re.compile(r"^D\d+\|", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedScannerPosition:
    line_number: int
    label_id: str
    pallet: str
    side: str


@dataclass(frozen=True)
class ParsedScannerProduct:
    line_number: int
    label_id: str
    internal_code: str
    quantity: int | None
    checksum: str
    position: ParsedScannerPosition | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ParsedDinamicScannerTxt:
    content_hash: str
    positions: tuple[ParsedScannerPosition, ...]
    products: tuple[ParsedScannerProduct, ...]
    parse_warnings: tuple[str, ...]


def _split_pipe_record(line: str, *, expected_parts: int, record_kind: str) -> tuple[list[str], tuple[str, ...]]:
    parts = line.split("|")
    if len(parts) != expected_parts:
        return parts, (f"{record_kind}:invalid_field_count",)
    return parts, ()


def _d1_errors_from_canonical(line: str) -> tuple[str, str, int | None, str, tuple[str, ...]]:
    """Validate D1 via domain parser; return extracted fields + error codes."""
    parsed = parse_product_label_payload(line)
    if parsed.status is ProductLabelValidationStatus.VALID:
        return (
            parsed.label_id or "",
            parsed.internal_code or "",
            parsed.quantity,
            parsed.checksum_received or "",
            (),
        )
    if parsed.status is ProductLabelValidationStatus.CHECKSUM_FAILED:
        return (
            parsed.label_id or "",
            parsed.internal_code or "",
            parsed.quantity,
            parsed.checksum_received or "",
            ("d1:checksum_failed",),
        )
    if parsed.status is ProductLabelValidationStatus.UNKNOWN_VERSION:
        return ("", "", None, "", ("d1:unknown_version",))
    if parsed.status is ProductLabelValidationStatus.MALFORMED:
        parts = line.split("|")
        return (
            (parts[1] if len(parts) > 1 else "").strip(),
            (parts[2] if len(parts) > 2 else "").strip(),
            None,
            (parts[4] if len(parts) > 4 else "").strip(),
            ("d1:malformed",),
        )
    return ("", "", None, "", ("d1:invalid",))


def _validate_position_fields(parts: list[str]) -> tuple[str, str, str, tuple[str, ...]]:
    errors: list[str] = []
    _kind, label_id, pallet, side = parts
    label = (label_id or "").strip()
    pallet_text = (pallet or "").strip()
    side_text = (side or "").strip()
    if not label:
        errors.append("position_label_id:required")
    if not pallet_text:
        errors.append("pallet:required")
    if not side_text:
        errors.append("side:required")
    else:
        try:
            PositionSide(side_text.strip().upper())
        except ValueError:
            errors.append("side:invalid")
    normalized_side = side_text.strip().upper() if not errors else side_text
    return label, pallet_text, normalized_side, tuple(errors)


def parse_dinamic_scanner_txt(
    content: bytes,
    *,
    max_lines: int = 50_000,
    max_line_length: int = 512,
) -> ParsedDinamicScannerTxt:
    """Parse TXT body sequentially; line order defines product→position association."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DinamicScannerTxtImportError(
            TXT_INVALID_ENCODING, "TXT must be UTF-8"
        ) from exc

    if not text.strip():
        raise DinamicScannerTxtImportError(TXT_EMPTY, "TXT file is empty")

    content_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
    current_position: ParsedScannerPosition | None = None
    positions: list[ParsedScannerPosition] = []
    products: list[ParsedScannerProduct] = []
    parse_warnings: list[str] = []
    non_empty_lines = 0

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if line_number > max_lines:
            raise DinamicScannerTxtImportError(
                TXT_TOO_MANY_LINES,
                f"TXT exceeds configured {max_lines} line limit",
            )
        if len(raw_line) > max_line_length:
            raise DinamicScannerTxtImportError(
                TXT_LINE_TOO_LONG,
                f"Line {line_number} exceeds {max_line_length} character limit",
            )
        line = raw_line.strip()
        if not line:
            continue
        non_empty_lines += 1

        if line.startswith(_POSITION_PREFIX):
            parts, count_errors = _split_pipe_record(line, expected_parts=4, record_kind="POSITION")
            if count_errors:
                parse_warnings.append(f"line {line_number}: {';'.join(count_errors)}")
                current_position = None
                continue
            label, pallet, side, field_errors = _validate_position_fields(parts)
            if field_errors:
                parse_warnings.append(f"line {line_number}: {';'.join(field_errors)}")
                current_position = None
                continue
            current_position = ParsedScannerPosition(
                line_number=line_number,
                label_id=label,
                pallet=pallet,
                side=side,
            )
            positions.append(current_position)
            continue

        if _VERSIONED_PRODUCT_PATTERN.match(line):
            label_id = ""
            internal_code = ""
            quantity: int | None = None
            checksum = ""
            label_id, internal_code, quantity, checksum, field_errors = _d1_errors_from_canonical(
                line
            )
            errors = list(field_errors)
            position = current_position
            if current_position is None:
                errors.append("product:no_valid_active_position")
            products.append(
                ParsedScannerProduct(
                    line_number=line_number,
                    label_id=label_id,
                    internal_code=internal_code,
                    quantity=quantity,
                    checksum=checksum,
                    position=position,
                    errors=tuple(dict.fromkeys(errors)),
                    warnings=(),
                )
            )
            continue

        parse_warnings.append(f"line {line_number}: unknown_record")

    if non_empty_lines == 0:
        raise DinamicScannerTxtImportError(TXT_EMPTY, "TXT file contains no data lines")

    return ParsedDinamicScannerTxt(
        content_hash=content_hash,
        positions=tuple(positions),
        products=tuple(products),
        parse_warnings=tuple(parse_warnings),
    )


def aisle_code_from_txt_filename(filename: str | None) -> str:
    """Derive aisle code from upload filename (basename without .txt extension)."""
    if not filename or not str(filename).strip():
        raise DinamicScannerTxtImportError(
            TXT_FILENAME_REQUIRED, "TXT upload must include a filename"
        )
    raw = str(filename).strip()
    if ".." in raw or "/" in raw or "\\" in raw:
        raise DinamicScannerTxtImportError(
            TXT_INVALID_FILENAME, "TXT filename is not allowed"
        )
    base = raw
    if not base or base in {".", ".."}:
        raise DinamicScannerTxtImportError(
            TXT_INVALID_FILENAME, "TXT filename is not allowed"
        )
    lower = base.lower()
    if not lower.endswith(".txt"):
        raise DinamicScannerTxtImportError(
            TXT_INVALID_EXTENSION, "Upload filename must end with .txt"
        )
    code = base[:-4]
    if not code.strip():
        raise DinamicScannerTxtImportError(
            TXT_EMPTY_AISLE_NAME, "TXT filename must include an aisle name before .txt"
        )
    return code.strip()
