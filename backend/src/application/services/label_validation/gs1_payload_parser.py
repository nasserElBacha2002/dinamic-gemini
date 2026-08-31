"""GS1 element-string parser (PR2).

Normative sources (consulted 2026-08-31):
- GS1 General Specifications Release 26.0, Ratified Jan 2026
  (https://www.gs1.org/sites/default/files/docs/barcodes/GS1_General_Specifications.pdf)
  - §3.2 Table 3-1 Application Identifier formats / FNC1 requirements
  - §3.3.1 AI (00) SSCC N2+N18
  - §3.3.2 AI (01) GTIN N2+N14
  - §3.3.3 AI (02) CONTENT N2+N14
  - §3.4.1 AI (10) BATCH/LOT N2+X..20 (FNC1)
  - §3.4.7 AI (17) USE BY / EXPIRY N2+N6
  - §3.5.2 AI (21) SERIAL N2+X..20 (FNC1)
  - §3.6.5 AI (37) COUNT N2+N..8 (FNC1)
  - §7.8.3 / Table 7-6 predefined-length element strings (no separator when not last)
  - §7.8.4 separator character (FNC1 → ASCII GS / 0x1D in transmitted data)
  - §7.9.1 / GS1 check-digit service (Mod-10, odd positions from the right ×3)
  - https://www.gs1.org/services/how-calculate-check-digit-manually

Does not validate inventories, persist, or know tenants/suppliers/Vision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from src.domain.label_validation import LabelValidationErrorCode

# Transmitted Group Separator after scanners expand FNC1 (GS1 Gen Specs §7.8.4).
_GS = "\x1d"
_PAREN_AI_RE = re.compile(r"\((\d{2,4})\)")
_MAX_PAYLOAD = 512

# Table 7-6 (Gen Specs §7.8.3): first two digits → total length including AI digits.
_PREDEFINED_TOTAL_LEN_BY_AI_PREFIX: dict[str, int] = {
    "00": 20,
    "01": 16,
    "02": 16,
    "03": 16,
    "04": 18,
    "11": 8,
    "12": 8,
    "13": 8,
    "14": 8,
    "15": 8,
    "16": 8,
    "17": 8,
    "18": 8,
    "19": 8,
    "20": 4,
    "31": 10,
    "32": 10,
    "33": 10,
    "34": 10,
    "35": 10,
    "36": 10,
    "41": 16,
}


class Gs1AiDataKind(str, Enum):
    NUMERIC_FIXED = "NUMERIC_FIXED"
    ALNUM_VARIABLE = "ALNUM_VARIABLE"
    NUMERIC_VARIABLE = "NUMERIC_VARIABLE"
    DATE_YYMMDD = "DATE_YYMMDD"


@dataclass(frozen=True)
class Gs1AiDefinition:
    ai: str
    kind: Gs1AiDataKind
    data_length: int | None  # fixed length when not variable
    max_length: int
    fnc1_required: bool
    check_digit: bool = False


# MVP AI dictionary — formats from Gen Specs Table 3-1.
_MVP_AIS: dict[str, Gs1AiDefinition] = {
    "00": Gs1AiDefinition("00", Gs1AiDataKind.NUMERIC_FIXED, 18, 18, False, True),
    "01": Gs1AiDefinition("01", Gs1AiDataKind.NUMERIC_FIXED, 14, 14, False, True),
    "02": Gs1AiDefinition("02", Gs1AiDataKind.NUMERIC_FIXED, 14, 14, False, True),
    "10": Gs1AiDefinition("10", Gs1AiDataKind.ALNUM_VARIABLE, None, 20, True),
    "17": Gs1AiDefinition("17", Gs1AiDataKind.DATE_YYMMDD, 6, 6, False),
    "21": Gs1AiDefinition("21", Gs1AiDataKind.ALNUM_VARIABLE, None, 20, True),
    "37": Gs1AiDefinition("37", Gs1AiDataKind.NUMERIC_VARIABLE, None, 8, True),
}


@dataclass(frozen=True)
class Gs1ParsedField:
    ai: str
    raw_value: str
    normalized_value: str
    known: bool
    title: str | None = None


@dataclass(frozen=True)
class Gs1ParseResult:
    raw_payload: str
    encoded_payload: str
    fields: tuple[Gs1ParsedField, ...] = ()
    error_code: str | None = None
    detail: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error_code is None

    def by_ai(self) -> dict[str, Gs1ParsedField]:
        return {f.ai: f for f in self.fields if f.known}


def gs1_mod10_check_digit(body_without_check: str) -> int:
    """GS1 standard Mod-10 check digit (Gen Specs §7.9.1 / gs1.org check-digit service)."""
    if not body_without_check.isdigit():
        raise ValueError("check digit body must be numeric")
    total = 0
    for i, ch in enumerate(reversed(body_without_check)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - (total % 10)) % 10


def verify_gs1_check_digit(value_with_check: str) -> bool:
    if not value_with_check.isdigit() or len(value_with_check) < 2:
        return False
    expected = gs1_mod10_check_digit(value_with_check[:-1])
    return expected == int(value_with_check[-1])


class Gs1PayloadParser:
    """raw GS1 payload → Application Identifier fields (no inventory/tenant knowledge)."""

    def parse(self, raw_payload: str) -> Gs1ParseResult:
        raw = raw_payload if raw_payload is not None else ""
        if len(raw) > _MAX_PAYLOAD:
            return Gs1ParseResult(
                raw_payload=raw,
                encoded_payload=raw,
                error_code=LabelValidationErrorCode.LABEL_GS1_INVALID.value,
                detail="GS1 payload exceeds length limit",
            )
        stripped = raw.strip()
        if not stripped:
            return Gs1ParseResult(
                raw_payload=raw,
                encoded_payload="",
                error_code=LabelValidationErrorCode.LABEL_GS1_INVALID.value,
                detail="empty GS1 payload",
            )

        if "(" in stripped and ")" in stripped:
            return self._parse_parenthesized(raw=raw, text=stripped)
        return self._parse_encoded(raw=raw, text=_normalize_encoded(stripped))

    def _parse_parenthesized(self, *, raw: str, text: str) -> Gs1ParseResult:
        matches = list(_PAREN_AI_RE.finditer(text))
        if not matches:
            return Gs1ParseResult(
                raw_payload=raw,
                encoded_payload=text,
                error_code=LabelValidationErrorCode.LABEL_GS1_INVALID.value,
                detail="parenthesized GS1 payload has no Application Identifiers",
            )
        fields: list[Gs1ParsedField] = []
        for idx, match in enumerate(matches):
            ai = match.group(1)
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            value = text[start:end]
            parsed = self._validate_ai_value(ai, value, require_separator_consumed=True)
            if isinstance(parsed, Gs1ParseResult):
                return Gs1ParseResult(
                    raw_payload=raw,
                    encoded_payload=text,
                    error_code=parsed.error_code,
                    detail=parsed.detail,
                    diagnostics=parsed.diagnostics,
                )
            fields.append(parsed)
        return Gs1ParseResult(raw_payload=raw, encoded_payload=text, fields=tuple(fields))

    def _parse_encoded(self, *, raw: str, text: str) -> Gs1ParseResult:
        pos = 0
        fields: list[Gs1ParsedField] = []
        length = len(text)
        steps = 0
        while pos < length:
            steps += 1
            if steps > _MAX_PAYLOAD:
                return Gs1ParseResult(
                    raw_payload=raw,
                    encoded_payload=text,
                    error_code=LabelValidationErrorCode.LABEL_GS1_INVALID.value,
                    detail="GS1 parse exceeded step bound",
                )
            if text[pos] == _GS:
                pos += 1
                continue
            ai = _match_ai(text, pos)
            if ai is None:
                return Gs1ParseResult(
                    raw_payload=raw,
                    encoded_payload=text,
                    error_code=LabelValidationErrorCode.LABEL_GS1_INVALID.value,
                    detail=f"malformed Application Identifier at offset {pos}",
                    diagnostics={"offset": pos},
                )
            pos += len(ai)
            definition = _MVP_AIS.get(ai)
            if definition is not None:
                value, pos, err = self._read_defined_value(text, pos, definition)
                if err is not None:
                    return Gs1ParseResult(
                        raw_payload=raw,
                        encoded_payload=text,
                        error_code=err[0],
                        detail=err[1],
                    )
                validated = self._validate_ai_value(
                    ai, value, require_separator_consumed=True
                )
                if isinstance(validated, Gs1ParseResult):
                    return Gs1ParseResult(
                        raw_payload=raw,
                        encoded_payload=text,
                        error_code=validated.error_code,
                        detail=validated.detail,
                        diagnostics=validated.diagnostics,
                    )
                fields.append(validated)
                continue

            # Unknown AI — preserve when length is unambiguous (Table 7-6 or GS).
            data_len = _ai_data_length_for_predefined(ai)
            if data_len is not None:
                if data_len < 0 or pos + data_len > length:
                    return Gs1ParseResult(
                        raw_payload=raw,
                        encoded_payload=text,
                        error_code=LabelValidationErrorCode.LABEL_GS1_INVALID.value,
                        detail=f"truncated unknown predefined-length AI {ai}",
                    )
                value = text[pos : pos + data_len]
                pos += data_len
                fields.append(
                    Gs1ParsedField(
                        ai=ai,
                        raw_value=value,
                        normalized_value=value,
                        known=False,
                    )
                )
                continue

            gs_at = text.find(_GS, pos)
            if gs_at >= 0:
                value = text[pos:gs_at]
                pos = gs_at + 1
            else:
                value = text[pos:]
                pos = length
            if not value:
                return Gs1ParseResult(
                    raw_payload=raw,
                    encoded_payload=text,
                    error_code=LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
                    detail=f"empty data for unknown AI {ai}",
                )
            fields.append(
                Gs1ParsedField(
                    ai=ai, raw_value=value, normalized_value=value, known=False
                )
            )
        return Gs1ParseResult(raw_payload=raw, encoded_payload=text, fields=tuple(fields))

    def _read_defined_value(
        self, text: str, pos: int, definition: Gs1AiDefinition
    ) -> tuple[str, int, tuple[str, str] | None]:
        length = len(text)
        if definition.kind in (
            Gs1AiDataKind.NUMERIC_FIXED,
            Gs1AiDataKind.DATE_YYMMDD,
        ):
            data_len = int(definition.data_length or 0)
            if pos + data_len > length:
                return (
                    "",
                    pos,
                    (
                        LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
                        f"truncated AI {definition.ai} data",
                    ),
                )
            value = text[pos : pos + data_len]
            return value, pos + data_len, None

        # Variable-length: FNC1/GS required unless this is the last element string.
        gs_at = text.find(_GS, pos)
        if gs_at >= 0:
            value = text[pos:gs_at]
            new_pos = gs_at + 1
        else:
            value = text[pos:]
            new_pos = length
            # If another AI would follow without separator → invalid (Gen Specs §7.8.4).
            # Detect only when remainder exceeds max (leftover after max) — fail closed.
            if len(value) > definition.max_length:
                return (
                    "",
                    pos,
                    (
                        LabelValidationErrorCode.LABEL_GS1_SEPARATOR_INVALID.value,
                        (
                            f"AI {definition.ai} exceeds max length without "
                            "Group Separator (FNC1)"
                        ),
                    ),
                )
        if len(value) > definition.max_length:
            return (
                "",
                pos,
                (
                    LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
                    f"AI {definition.ai} exceeds max length {definition.max_length}",
                ),
            )
        if not value:
            return (
                "",
                pos,
                (
                    LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
                    f"AI {definition.ai} data is empty",
                ),
            )
        return value, new_pos, None

    def _validate_ai_value(
        self, ai: str, value: str, *, require_separator_consumed: bool
    ) -> Gs1ParsedField | Gs1ParseResult:
        del require_separator_consumed
        definition = _MVP_AIS.get(ai)
        if definition is None:
            return Gs1ParsedField(
                ai=ai, raw_value=value, normalized_value=value, known=False
            )

        if definition.kind is Gs1AiDataKind.NUMERIC_FIXED:
            if not value.isdigit() or len(value) != int(definition.data_length or 0):
                return Gs1ParseResult(
                    raw_payload="",
                    encoded_payload="",
                    error_code=LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
                    detail=f"AI {ai} must be {definition.data_length} numeric digits",
                )
            if definition.check_digit and not verify_gs1_check_digit(value):
                return Gs1ParseResult(
                    raw_payload="",
                    encoded_payload="",
                    error_code=LabelValidationErrorCode.LABEL_GS1_CHECK_DIGIT_FAILED.value,
                    detail=f"AI {ai} check digit failed",
                    diagnostics={"ai": ai, "value": value},
                )
            return Gs1ParsedField(
                ai=ai,
                raw_value=value,
                normalized_value=value,
                known=True,
                title=_title_for(ai),
            )

        if definition.kind is Gs1AiDataKind.DATE_YYMMDD:
            normalized = _normalize_expiry_yymmdd(value)
            if normalized is None:
                return Gs1ParseResult(
                    raw_payload="",
                    encoded_payload="",
                    error_code=LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
                    detail=f"AI {ai} expiration date is invalid",
                    diagnostics={"ai": ai, "raw_value": value},
                )
            return Gs1ParsedField(
                ai=ai,
                raw_value=value,
                normalized_value=normalized,
                known=True,
                title=_title_for(ai),
            )

        if definition.kind is Gs1AiDataKind.NUMERIC_VARIABLE:
            if not value.isdigit() or len(value) > definition.max_length:
                return Gs1ParseResult(
                    raw_payload="",
                    encoded_payload="",
                    error_code=LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
                    detail=f"AI {ai} must be 1..{definition.max_length} digits",
                )
            return Gs1ParsedField(
                ai=ai,
                raw_value=value,
                normalized_value=value,
                known=True,
                title=_title_for(ai),
            )

        # ALNUM_VARIABLE — GS1 AI encodable set approximated as printable non-GS.
        if _GS in value or len(value) > definition.max_length:
            return Gs1ParseResult(
                raw_payload="",
                encoded_payload="",
                error_code=LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
                detail=f"AI {ai} alphanumeric field invalid",
            )
        if not all(32 <= ord(ch) <= 126 for ch in value):
            return Gs1ParseResult(
                raw_payload="",
                encoded_payload="",
                error_code=LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
                detail=f"AI {ai} contains unsupported characters",
            )
        return Gs1ParsedField(
            ai=ai,
            raw_value=value,
            normalized_value=value,
            known=True,
            title=_title_for(ai),
        )


def _normalize_encoded(text: str) -> str:
    # Leading FNC1 sometimes appears as "]C1" / "]e0" symbology identifiers — strip common forms.
    out = text
    for prefix in ("]C1", "]e0", "]d2", "]Q3"):
        if out.startswith(prefix):
            out = out[len(prefix) :]
            break
    if out.startswith(_GS):
        out = out[1:]
    return out


def _match_ai(text: str, pos: int) -> str | None:
    """Match AI digit prefix at ``pos``.

    MVP AIs are 2-digit. For Table 7-6 ranges 31–36 the AI is 4 digits; for 41x it is 3.
    """
    if pos + 2 > len(text) or not text[pos : pos + 2].isdigit():
        return None
    prefix = text[pos : pos + 2]
    if prefix in _MVP_AIS:
        return prefix
    if prefix in {"31", "32", "33", "34", "35", "36"}:
        if pos + 4 <= len(text) and text[pos : pos + 4].isdigit():
            return text[pos : pos + 4]
        return None
    if prefix == "41":
        if pos + 3 <= len(text) and text[pos : pos + 3].isdigit():
            return text[pos : pos + 3]
        return None
    if prefix in _PREDEFINED_TOTAL_LEN_BY_AI_PREFIX:
        return prefix
    # Unknown 2-digit AI — accept token; variable unknown handling applies.
    return prefix


def _ai_data_length_for_predefined(ai: str) -> int | None:
    prefix = ai[:2]
    total = _PREDEFINED_TOTAL_LEN_BY_AI_PREFIX.get(prefix)
    if total is None:
        return None
    return total - len(ai)


def _title_for(ai: str) -> str:
    return {
        "00": "SSCC",
        "01": "GTIN",
        "02": "CONTENT",
        "10": "BATCH/LOT",
        "17": "USE BY/EXPIRY",
        "21": "SERIAL",
        "37": "COUNT",
    }.get(ai, ai)


def _normalize_expiry_yymmdd(value: str) -> str | None:
    """Validate YYMMDD per Gen Specs; DD=00 means last day of month is not expanded here.

    Invalid calendar dates are rejected (no silent coercion). DD=00 accepted as month-only
    per Gen Specs note (2) on date AIs.
    """
    if not value.isdigit() or len(value) != 6:
        return None
    yy = int(value[0:2])
    mm = int(value[2:4])
    dd = int(value[4:6])
    if mm < 1 or mm > 12:
        return None
    # Century window: Gen Specs §7.12 — keep YY as-is in normalized ISO-like form.
    year = 2000 + yy if yy < 80 else 1900 + yy
    if dd == 0:
        return f"{year:04d}-{mm:02d}"
    try:
        date(year, mm, dd)
    except ValueError:
        return None
    return f"{year:04d}-{mm:02d}-{dd:02d}"
