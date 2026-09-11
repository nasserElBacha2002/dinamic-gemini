"""Parse Dinamic Scanner ESP32 aisle TXT exports (POSITION + D1 records).

Optional SUPPLIER extraction profiles enable generic SIMPLE/SEGMENTED payloads on the
same sequential POSITION→product association model — without hardcoding supplier prefixes.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from src.application.services.position_recognition import (
    PositionCodeNormalizationError,
    normalize_position_code,
)
from src.domain.client_position_label.hierarchy import PositionSide
from src.domain.client_supplier.extraction_profile import ExtractionProfileConfiguration
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
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationStatus,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext
from src.domain.product_labels.format import (
    ProductLabelValidationStatus,
    parse_product_label_payload,
)

_POSITION_PREFIX = "POSITION|"
_VERSIONED_PRODUCT_PATTERN = re.compile(r"^D\d+\|", re.IGNORECASE)
# Explicitly prohibited JSON Dinamic position payloads in TXT (legacy rule).
_FORBIDDEN_JSON_POSITION = re.compile(r"DINAMIC_POSITION|\"type\"\s*:\s*\"DINAMIC", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedScannerPosition:
    line_number: int
    label_id: str
    pallet: str | None
    side: str | None


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


def _split_pipe_record(
    line: str, *, expected_parts: int, record_kind: str
) -> tuple[list[str], tuple[str, ...]]:
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
    else:
        try:
            normalize_position_code(label)
        except PositionCodeNormalizationError as exc:
            suffix = {
                "POSITION_CODE_TOO_LONG": "too_long",
                "POSITION_CODE_CONTROL_CHARACTER": "control_character",
            }.get(exc.code, "invalid")
            errors.append(f"position_label_id:{suffix}")
    if not pallet_text:
        errors.append("pallet:required")
    elif any(unicodedata.category(ch).startswith("C") for ch in pallet_text):
        errors.append("pallet:control_character")
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
    validation_context: LabelValidationContext | None = None,
    item_configuration: ExtractionProfileConfiguration | None = None,
    position_configuration: ExtractionProfileConfiguration | None = None,
) -> ParsedDinamicScannerTxt:
    """Parse TXT body sequentially; line order defines product→position association.

    Prefer ``validation_context`` with real resolved profiles / snapshotted configs.
    Optional ``item_configuration`` / ``position_configuration`` remain for unit tests
    and build an ephemeral context without fabricating supplier/profile ids.
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DinamicScannerTxtImportError(TXT_INVALID_ENCODING, "TXT must be UTF-8") from exc

    if not text.strip():
        raise DinamicScannerTxtImportError(TXT_EMPTY, "TXT file is empty")

    content_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
    current_position: ParsedScannerPosition | None = None
    positions: list[ParsedScannerPosition] = []
    products: list[ParsedScannerProduct] = []
    parse_warnings: list[str] = []
    non_empty_lines = 0

    label_svc = None
    validation_ctx = validation_context
    if validation_ctx is None and (
        item_configuration is not None or position_configuration is not None
    ):
        from src.application.services.label_validation.label_validation_service import (
            LabelValidationService,
        )

        label_svc = LabelValidationService()
        item_src = (
            LabelProfileSource.SUPPLIER
            if item_configuration is not None
            else LabelProfileSource.DINAMIC
        )
        pos_src = (
            LabelProfileSource.SUPPLIER
            if position_configuration is not None
            else LabelProfileSource.DINAMIC
        )
        validation_ctx = LabelValidationContext(
            resolved_profiles=ResolvedLabelProfiles(
                item=ResolvedLabelProfile(
                    label_kind=LabelKind.ITEM,
                    source=item_src,
                    client_supplier_id=None,
                    resolution_source="EPHEMERAL_TXT",
                ),
                position=ResolvedLabelProfile(
                    label_kind=LabelKind.POSITION,
                    source=pos_src,
                    client_supplier_id=None,
                    resolution_source="EPHEMERAL_TXT",
                ),
            ),
            item_extraction_configuration=item_configuration,
            position_extraction_configuration=position_configuration,
        )
    elif validation_ctx is not None:
        from src.application.services.label_validation.label_validation_service import (
            LabelValidationService,
        )

        label_svc = LabelValidationService()

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

        if _FORBIDDEN_JSON_POSITION.search(line):
            parse_warnings.append(f"line {line_number}: forbidden_dinamic_position_json")
            continue

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

        if label_svc is not None and validation_ctx is not None:
            result = label_svc.validate_best_effort(
                CandidateLabel(
                    raw_payload=line,
                    recognition_source=RecognitionSource.TXT,
                ),
                context=validation_ctx,
            )
            dual = result.diagnostics or {}
            if result.status is LabelValidationStatus.VALID and result.label_kind is LabelKind.POSITION:
                pos_id = getattr(result.label, "position_id", None) or line
                pallet_raw = getattr(result.label, "pallet", None)
                side_raw = getattr(result.label, "side", None)
                pallet = str(pallet_raw).strip() if pallet_raw else None
                side = str(side_raw).strip().upper() if side_raw else None
                current_position = ParsedScannerPosition(
                    line_number=line_number,
                    label_id=str(pos_id).strip(),
                    pallet=pallet or None,
                    side=side or None,
                )
                positions.append(current_position)
                continue
            if result.status is LabelValidationStatus.VALID and result.label_kind is LabelKind.ITEM:
                label_id = (getattr(result.label, "label_id", None) or "").strip()
                sku = (getattr(result.label, "sku", None) or "").strip() or label_id
                qty_raw = getattr(result.label, "quantity", None)
                quantity = int(qty_raw) if qty_raw is not None else None
                errors_list: list[str] = []
                if current_position is None:
                    errors_list.append("product:no_valid_active_position")
                products.append(
                    ParsedScannerProduct(
                        line_number=line_number,
                        label_id=label_id,
                        internal_code=sku,
                        quantity=quantity,
                        checksum="",
                        position=current_position,
                        errors=tuple(dict.fromkeys(errors_list)),
                        warnings=(),
                    )
                )
                continue
            if result.status is LabelValidationStatus.AMBIGUOUS:
                parse_warnings.append(f"line {line_number}: ambiguous_label_kind")
                continue
            if result.status is LabelValidationStatus.INVALID:
                item_err = (dual.get("item_validation") or {}).get("error_code")
                pos_err = (dual.get("position_validation") or {}).get("error_code")
                detail = result.error_code or "supplier_invalid"
                parse_warnings.append(
                    f"line {line_number}: {detail}"
                    + (f";item={item_err}" if item_err else "")
                    + (f";position={pos_err}" if pos_err else "")
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
        raise DinamicScannerTxtImportError(TXT_INVALID_FILENAME, "TXT filename is not allowed")
    base = raw
    if not base or base in {".", ".."}:
        raise DinamicScannerTxtImportError(TXT_INVALID_FILENAME, "TXT filename is not allowed")
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
