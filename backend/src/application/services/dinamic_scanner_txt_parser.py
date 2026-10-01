"""Parse Dinamic Scanner ESP32 aisle TXT exports (POSITION + D1 records).

Optional SUPPLIER extraction profiles enable generic SIMPLE/SEGMENTED payloads on the
same sequential POSITION→product association model — without hardcoding supplier prefixes.

Transport also accepts inventory ITEM lines ``<identifier>|<quantity>`` (Raspberry raw).
Identifier validation uses the resolved ITEM profile when available; uniqueness/dedupe
follows existing profile semantics (unique instance label_id vs product SKU).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from src.application.services.code_scan_qr_payload import (
    _PIPE_PATTERN,
    parse_inventory_code_payload,
)
from src.application.services.position_recognition import (
    PositionCodeNormalizationError,
    normalize_position_code,
)
from src.domain.client_position_label.hierarchy import PositionSide
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    ItemLabelSemanticType,
)
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

_UNIQUE_INSTANCE_SEMANTICS = frozenset(
    {
        ItemLabelSemanticType.LPN.value,
        ItemLabelSemanticType.SSCC.value,
        ItemLabelSemanticType.LOGISTIC_UNIT.value,
        ItemLabelSemanticType.PALLET.value,
        ItemLabelSemanticType.BOX.value,
        ItemLabelSemanticType.CONTAINER.value,
    }
)


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


def _try_parse_item_pipe_transport(line: str) -> tuple[str, int] | None:
    """Transport-level ``identifier|quantity`` (same grammar as inventory CODE_QUANTITY_PIPE)."""
    text = (line or "").strip()
    if not text or not _PIPE_PATTERN.match(text):
        return None
    # Reject Dinamic POSITION / versioned D1 which share pipes but are handled upstream.
    if text.upper().startswith("POSITION|") or _VERSIONED_PRODUCT_PATTERN.match(text):
        return None
    try:
        parsed = parse_inventory_code_payload(text)
    except ValueError:
        return None
    code = str(parsed.get("internal_code") or "").strip()
    qty = parsed.get("quantity")
    if not code or qty is None:
        return None
    return code, int(qty)


def scanner_txt_has_pipe_item_transport(content: bytes) -> bool:
    """True when UTF-8 TXT contains at least one ``identifier|quantity`` transport line."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _FORBIDDEN_JSON_POSITION.search(line):
            continue
        if line.startswith(_POSITION_PREFIX) or _VERSIONED_PRODUCT_PATTERN.match(line):
            continue
        if _try_parse_item_pipe_transport(line) is not None:
            return True
    return False


def is_unique_instance_item_identity(
    *,
    item_configuration: ExtractionProfileConfiguration | None,
    label_id: str,
    sku: str,
) -> bool:
    """Whether ``label_id`` represents a count-once physical/instance id.

    Reuses profile semantics already present in the domain (MINIMAL / logistic /
    PRODUCT_SKU). Does not infer uniqueness from the code text alone.
    """
    label = (label_id or "").strip()
    if not label:
        return False
    if item_configuration is None:
        # Dinamic D1 path supplies a real unique label_id without supplier config.
        return True
    semantic = (item_configuration.semantic_type or "").strip().upper()
    if semantic == ItemLabelSemanticType.PRODUCT_SKU.value:
        return False
    if item_configuration.is_minimal():
        return True
    if semantic in _UNIQUE_INSTANCE_SEMANTICS:
        return True
    required = {
        f.strip().lower()
        for f in item_configuration.required_fields
        if f and str(f).strip()
    }
    identity = required & {"label_id", "sku", "internal_code"}
    if identity and identity <= {"sku", "internal_code"}:
        return False
    if "label_id" in identity and not ({"sku", "internal_code"} & identity):
        return True
    # label_id + sku both required but equal → product code mapped into both fields;
    # do not treat as unique instance without an explicit unique semantic above.
    code = (sku or "").strip()
    if label and code and label == code:
        return False
    return "label_id" in identity


def _item_fields_for_product(
    *,
    item_configuration: ExtractionProfileConfiguration | None,
    label_id: str,
    sku: str,
    quantity: int | None,
    unique_instance: bool | None = None,
) -> tuple[str, str, int | None]:
    """Map validated fields to CSV label_id / internal_code for claim semantics."""
    lid = (label_id or "").strip()
    code = (sku or "").strip() or lid
    unique = (
        unique_instance
        if unique_instance is not None
        else is_unique_instance_item_identity(
            item_configuration=item_configuration, label_id=lid, sku=code
        )
    )
    if unique:
        return lid, code, quantity
    # Product SKU / non-unique identity: never populate label_id for count-once claims.
    return "", code, quantity


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
    effective_item_config = item_configuration
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
        if effective_item_config is None:
            effective_item_config = validation_ctx.item_extraction_configuration

    # First *valid* unique-instance identity per physical label_id:
    # (normalized_internal_code, quantity). Invalid rows never reserve a slot.
    seen_unique_instances: dict[str, tuple[str, int | None]] = {}

    def _append_product(
        *,
        line_number: int,
        label_id: str,
        internal_code: str,
        quantity: int | None,
        checksum: str = "",
        errors: list[str] | tuple[str, ...] = (),
        unique_instance: bool,
        require_active_position: bool = True,
    ) -> None:
        nonlocal products
        errors_list = list(errors)
        claim_label = (label_id or "").strip()
        position = current_position
        # D1 / versioned stickers require sequential POSITION association.
        # Raspberry ``identifier|quantity`` (and supplier ITEM) may arrive without
        # POSITION; CSV converter marks those rows requires_review when position_code empty.
        if require_active_position and current_position is None:
            errors_list.append("product:no_valid_active_position")
        final_errors = tuple(dict.fromkeys(errors_list))
        is_valid = len(final_errors) == 0
        identity = ((internal_code or "").strip(), quantity)

        if unique_instance and claim_label:
            key = claim_label.upper()
            prior = seen_unique_instances.get(key)
            if prior is not None:
                if prior == identity:
                    # Same physical sticker + same content: count-once.
                    parse_warnings.append(f"line {line_number}: duplicate_unique_label_id")
                    return
                # Same physical id, different SKU/qty: observable conflict (do not omit silently).
                parse_warnings.append(f"line {line_number}: unique_label_id_identity_conflict")
                products.append(
                    ParsedScannerProduct(
                        line_number=line_number,
                        label_id=claim_label,
                        internal_code=internal_code,
                        quantity=quantity,
                        checksum=checksum,
                        position=position,
                        errors=tuple(
                            dict.fromkeys((*final_errors, "unique_label_id:identity_conflict"))
                        ),
                        warnings=(),
                    )
                )
                return
            if is_valid:
                seen_unique_instances[key] = identity
        elif not unique_instance:
            claim_label = ""

        products.append(
            ParsedScannerProduct(
                line_number=line_number,
                label_id=claim_label,
                internal_code=internal_code,
                quantity=quantity,
                checksum=checksum,
                position=position,
                errors=final_errors,
                warnings=(),
            )
        )

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
            label_id, internal_code, quantity, checksum, field_errors = _d1_errors_from_canonical(
                line
            )
            # D1 physical stickers are unique instance ids (existing count-once semantics).
            _append_product(
                line_number=line_number,
                label_id=label_id,
                internal_code=internal_code,
                quantity=quantity,
                checksum=checksum,
                errors=field_errors,
                unique_instance=bool((label_id or "").strip()),
            )
            continue

        pipe_transport = _try_parse_item_pipe_transport(line)

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
                supplier_pallet: str | None = (
                    str(pallet_raw).strip() if pallet_raw else None
                )
                supplier_side: str | None = (
                    str(side_raw).strip().upper() if side_raw else None
                )
                current_position = ParsedScannerPosition(
                    line_number=line_number,
                    label_id=str(pos_id).strip(),
                    pallet=supplier_pallet or None,
                    side=supplier_side or None,
                )
                positions.append(current_position)
                continue
            if result.status is LabelValidationStatus.VALID and result.label_kind is LabelKind.ITEM:
                label_id = (getattr(result.label, "label_id", None) or "").strip()
                sku = (getattr(result.label, "sku", None) or "").strip() or label_id
                qty_raw = getattr(result.label, "quantity", None)
                quantity = int(qty_raw) if qty_raw is not None else None
                if quantity is None and pipe_transport is not None:
                    quantity = pipe_transport[1]
                claim_label, internal_code, quantity = _item_fields_for_product(
                    item_configuration=effective_item_config,
                    label_id=label_id,
                    sku=sku,
                    quantity=quantity,
                )
                unique = is_unique_instance_item_identity(
                    item_configuration=effective_item_config,
                    label_id=label_id,
                    sku=sku,
                )
                _append_product(
                    line_number=line_number,
                    label_id=claim_label,
                    internal_code=internal_code,
                    quantity=quantity,
                    unique_instance=unique,
                    require_active_position=False,
                )
                continue

            # Full-line profile miss: for ``id|qty`` transport, validate identifier alone.
            if pipe_transport is not None:
                identifier, pipe_qty = pipe_transport
                id_result = label_svc.validate_best_effort(
                    CandidateLabel(
                        raw_payload=identifier,
                        recognition_source=RecognitionSource.TXT,
                    ),
                    context=validation_ctx,
                )
                if (
                    id_result.status is LabelValidationStatus.VALID
                    and id_result.label_kind is LabelKind.ITEM
                ):
                    label_id = (getattr(id_result.label, "label_id", None) or "").strip()
                    sku = (
                        (getattr(id_result.label, "sku", None) or "").strip()
                        or label_id
                        or identifier
                    )
                    qty_raw = getattr(id_result.label, "quantity", None)
                    quantity = int(qty_raw) if qty_raw is not None else pipe_qty
                    claim_label, internal_code, quantity = _item_fields_for_product(
                        item_configuration=effective_item_config,
                        label_id=label_id,
                        sku=sku,
                        quantity=quantity,
                    )
                    unique = is_unique_instance_item_identity(
                        item_configuration=effective_item_config,
                        label_id=label_id,
                        sku=sku,
                    )
                    _append_product(
                        line_number=line_number,
                        label_id=claim_label,
                        internal_code=internal_code,
                        quantity=quantity,
                        unique_instance=unique,
                        require_active_position=False,
                    )
                    continue
                if id_result.status is LabelValidationStatus.AMBIGUOUS:
                    parse_warnings.append(f"line {line_number}: ambiguous_label_kind")
                    continue
                if id_result.status is LabelValidationStatus.INVALID:
                    id_dual = id_result.diagnostics or {}
                    item_err = (id_dual.get("item_validation") or {}).get("error_code")
                    detail = id_result.error_code or "supplier_invalid"
                    parse_warnings.append(
                        f"line {line_number}: {detail}"
                        + (f";item={item_err}" if item_err else "")
                        + ";pipe_identifier"
                    )
                    continue
                parse_warnings.append(
                    f"line {line_number}: pipe_identifier_unvalidated"
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

        elif pipe_transport is not None:
            # Transport recognized but no profile context — do not silently accept as ITEM.
            parse_warnings.append(
                f"line {line_number}: pipe_item_requires_validation_context"
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
