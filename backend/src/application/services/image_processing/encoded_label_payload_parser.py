"""Phase 3 — parse an encoded label payload (QR / CODE128) into internal_code + quantity.

Thin, deterministic wrapper around
:func:`src.application.services.code_scan_qr_payload.parse_inventory_code_payload` that adds
validation and structured warnings on top of the shared payload grammar:

- ``internal_code|quantity`` pipe payload (primary)
- ``DI1|C=<urlencoded>|Q=<qty>`` legacy barcode
- plain code / labelled human QR (quantity unknown → ``quantity=None``)

Rules (no OCR, no LLM, no guessing):
- internal_code length 1..``CODE_MAX_LENGTH``; no control characters; leading zeros preserved.
- quantity: positive integer only, ``1..quantity_max``; no decimals.
- code present but quantity missing → ``quantity=None`` (caller marks PENDING_MANUAL_REVIEW).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from src.application.services.code_scan_qr_payload import (
    _DI1_PATTERN,
    _LABELED_CODE_PATTERN,
    _PIPE_PATTERN,
    parse_inventory_code_payload,
)

CODE_MAX_LENGTH = 48

# Contract v1.1 — reject PLAIN payloads that belong to other QR domains.
_PLAIN_REJECT_PREFIXES = (
    "http://",
    "https://",
    "WIFI:",
    "BEGIN:",
    "MECARD:",
    "MATMSG:",
    "SMTP:",
    "mailto:",
)
_EMAIL_PLAIN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", re.IGNORECASE)


class LabelPayloadFormat(str, Enum):
    PIPE = "PIPE"
    DI1 = "DI1"
    LABELED = "LABELED"
    PLAIN = "PLAIN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ParsedLabelPayload:
    format: LabelPayloadFormat
    version: str | None
    internal_code: str | None
    quantity: int | None
    raw_value: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_valid_code(self) -> bool:
        return bool(self.internal_code)

    @property
    def has_quantity(self) -> bool:
        return self.quantity is not None


def _has_control_chars(value: str) -> bool:
    return any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def _detect_format(raw: str) -> LabelPayloadFormat:
    text = (raw or "").strip()
    if _DI1_PATTERN.match(text):
        return LabelPayloadFormat.DI1
    if _PIPE_PATTERN.match(text):
        return LabelPayloadFormat.PIPE
    if _LABELED_CODE_PATTERN.search(text):
        return LabelPayloadFormat.LABELED
    return LabelPayloadFormat.PLAIN


def _is_rejected_plain_payload(code: str, raw: str) -> bool:
    text = (raw or "").strip()
    if "\n" in text and not _LABELED_CODE_PATTERN.search(text):
        return True
    lowered = code.strip()
    upper = text.upper()
    for prefix in _PLAIN_REJECT_PREFIXES:
        if lowered.lower().startswith(prefix.lower()) or upper.startswith(prefix.upper()):
            return True
    if text[:1] in "{[":
        return True
    if _EMAIL_PLAIN.match(lowered):
        return True
    return False


class EncodedLabelPayloadParser:
    """Parse + validate a single decoded code payload deterministically."""

    def __init__(
        self,
        *,
        quantity_max: int,
        allow_decimal_quantity: bool = False,
        code_max_length: int = CODE_MAX_LENGTH,
    ) -> None:
        self._quantity_max = int(quantity_max)
        self._allow_decimal = bool(allow_decimal_quantity)
        self._code_max_length = int(code_max_length)

    def parse(self, raw: str) -> ParsedLabelPayload:
        raw_value = raw if raw is not None else ""
        warnings: list[str] = []

        try:
            parsed = parse_inventory_code_payload(raw_value)
        except ValueError:
            return ParsedLabelPayload(
                format=LabelPayloadFormat.UNKNOWN,
                version=None,
                internal_code=None,
                quantity=None,
                raw_value=raw_value,
                warnings=("EMPTY_OR_UNPARSEABLE_PAYLOAD",),
            )

        fmt = _detect_format(raw_value)
        internal_code = parsed.get("internal_code")
        code = str(internal_code) if internal_code is not None else None
        raw_quantity = parsed.get("quantity")

        if not code:
            warnings.append("NO_INTERNAL_CODE")
            code = None
        elif len(code) < 1 or len(code) > self._code_max_length:
            warnings.append("CODE_LENGTH_OUT_OF_RANGE")
            code = None
        elif _has_control_chars(code):
            warnings.append("CODE_CONTROL_CHARACTERS")
            code = None
        elif fmt is LabelPayloadFormat.PLAIN and _is_rejected_plain_payload(code, raw_value):
            warnings.append("PLAIN_UNVERIFIED_PAYLOAD")
            code = None

        quantity: int | None = None
        if raw_quantity is None:
            warnings.append("QUANTITY_MISSING")
        elif isinstance(raw_quantity, float) and not self._allow_decimal:
            warnings.append("QUANTITY_DECIMAL_NOT_ALLOWED")
        else:
            try:
                qty_int = int(raw_quantity)
            except (TypeError, ValueError):
                warnings.append("QUANTITY_NOT_INTEGER")
                qty_int = None
            if qty_int is not None:
                if qty_int <= 0:
                    warnings.append("QUANTITY_NOT_POSITIVE")
                elif qty_int > self._quantity_max:
                    warnings.append("QUANTITY_ABOVE_MAX")
                else:
                    quantity = qty_int

        return ParsedLabelPayload(
            format=fmt,
            version="DI1" if fmt is LabelPayloadFormat.DI1 else None,
            internal_code=code,
            quantity=quantity,
            raw_value=raw_value,
            warnings=tuple(warnings),
        )


__all__ = [
    "CODE_MAX_LENGTH",
    "EncodedLabelPayloadParser",
    "LabelPayloadFormat",
    "ParsedLabelPayload",
]
