"""Versioned Dinamic product-label payload (physical label_id + read checksum).

Format D1 (pipe-separated, CODE128/QR friendly)::

    D1|<label_id>|<internal_code>|<quantity>|<checksum>

- ``label_id`` — identity of the physical sticker (not the SKU).
- ``checksum`` — read-integrity only (not authentication; not identity).
- Legacy PIPE / DI1 / PLAIN payloads remain parseable elsewhere without label_id.

Canonical charset for checksum body: uppercase A-Z and digits 0-9 only (other
characters in internal_code are included in the body string but hashed via their
ordinal contribution after uppercasing ASCII letters/digits; separators are ``|``).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from enum import Enum

PRODUCT_LABEL_FORMAT_VERSION = "D1"
PRODUCT_LABEL_PREFIX = "D1"
LABEL_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford-like, no I/L/O/U
LABEL_ID_LENGTH = 10
CHECKSUM_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

_D1_PATTERN = re.compile(
    r"^D1\|([0-9A-HJKMNP-TV-Z]{10})\|([^|\n]{1,48})\|([1-9]\d{0,7})\|([0-9A-Z])$",
    re.IGNORECASE,
)


class ProductLabelValidationStatus(str, Enum):
    VALID = "VALID"
    NOT_OUR_FORMAT = "NOT_OUR_FORMAT"
    CHECKSUM_FAILED = "CHECKSUM_FAILED"
    MALFORMED = "MALFORMED"
    UNKNOWN_VERSION = "UNKNOWN_VERSION"
    QUANTITY_INVALID = "QUANTITY_INVALID"
    LABEL_ID_INVALID = "LABEL_ID_INVALID"


@dataclass(frozen=True)
class ParsedProductLabelPayload:
    status: ProductLabelValidationStatus
    format_version: str | None
    label_id: str | None
    internal_code: str | None
    quantity: int | None
    checksum_received: str | None
    checksum_expected: str | None
    raw_value: str
    normalized_payload: str | None = None
    detail: str | None = None


def normalize_product_label_raw(raw: str) -> str:
    """Safe normalization before parse/checksum — trim only; no OCR substitutions."""
    return (raw or "").strip()


def generate_product_label_id(*, nbytes: int = 8) -> str:
    """Cryptographically strong label_id from alphabet (never recycle issued IDs)."""
    # Map random bytes into alphabet without modulo bias for small alphabets via rejection.
    out: list[str] = []
    alphabet = LABEL_ID_ALPHABET
    base = len(alphabet)
    while len(out) < LABEL_ID_LENGTH:
        for b in secrets.token_bytes(nbytes):
            if b >= 256 - (256 % base):
                continue
            out.append(alphabet[b % base])
            if len(out) >= LABEL_ID_LENGTH:
                break
    return "".join(out)


def _checksum_char(body: str) -> str:
    """Weighted Mod-36 checksum over uppercase body (integrity of reading only)."""
    total = 0
    for i, ch in enumerate(body.upper()):
        if ch in CHECKSUM_ALPHABET:
            val = CHECKSUM_ALPHABET.index(ch)
        else:
            val = ord(ch) % 36
        total = (total + (val * (i + 1))) % 36
    return CHECKSUM_ALPHABET[total]


def build_checksum_body(
    *,
    label_id: str,
    internal_code: str,
    quantity: int,
    format_version: str = PRODUCT_LABEL_FORMAT_VERSION,
) -> str:
    return f"{format_version}|{label_id}|{internal_code}|{quantity}"


def compute_product_label_checksum(
    *,
    label_id: str,
    internal_code: str,
    quantity: int,
    format_version: str = PRODUCT_LABEL_FORMAT_VERSION,
) -> str:
    return _checksum_char(
        build_checksum_body(
            label_id=label_id,
            internal_code=internal_code,
            quantity=quantity,
            format_version=format_version,
        )
    )


def build_product_label_payload(
    *,
    label_id: str,
    internal_code: str,
    quantity: int,
    format_version: str = PRODUCT_LABEL_FORMAT_VERSION,
) -> str:
    """Build canonical printable/scannable payload including checksum."""
    lid = label_id.strip().upper()
    code = internal_code.strip()
    if not re.fullmatch(rf"[{LABEL_ID_ALPHABET}]{{{LABEL_ID_LENGTH}}}", lid):
        raise ValueError("invalid label_id")
    if not code or "|" in code or len(code) > 48:
        raise ValueError("invalid internal_code")
    if not isinstance(quantity, int) or quantity < 1 or quantity > 99_999_999:
        raise ValueError("invalid quantity")
    cs = compute_product_label_checksum(
        label_id=lid, internal_code=code, quantity=quantity, format_version=format_version
    )
    return f"{format_version}|{lid}|{code}|{quantity}|{cs}"


def parse_product_label_payload(raw: str) -> ParsedProductLabelPayload:
    """Parse + validate D1 product labels. Non-D1 → NOT_OUR_FORMAT (caller may try legacy)."""
    text = normalize_product_label_raw(raw)
    if not text:
        return ParsedProductLabelPayload(
            status=ProductLabelValidationStatus.MALFORMED,
            format_version=None,
            label_id=None,
            internal_code=None,
            quantity=None,
            checksum_received=None,
            checksum_expected=None,
            raw_value=raw if raw is not None else "",
            detail="empty",
        )

    if text.upper().startswith("D") and text[1:2].isdigit() and not text.upper().startswith("D1|"):
        # Future / unknown version prefix D2|... etc.
        if re.match(r"^D\d+\|", text, re.IGNORECASE):
            return ParsedProductLabelPayload(
                status=ProductLabelValidationStatus.UNKNOWN_VERSION,
                format_version=text.split("|", 1)[0].upper(),
                label_id=None,
                internal_code=None,
                quantity=None,
                checksum_received=None,
                checksum_expected=None,
                raw_value=text,
                detail="unsupported format version",
            )

    match = _D1_PATTERN.match(text)
    if not match:
        # D1|… that fails strict grammar is still a D1 attempt — must not fall through
        # as NOT_OUR_FORMAT (that enables legacy revival on server-side consolidation).
        if text.upper().startswith("D1|"):
            parts = text.split("|")
            return ParsedProductLabelPayload(
                status=ProductLabelValidationStatus.MALFORMED,
                format_version=PRODUCT_LABEL_FORMAT_VERSION,
                label_id=parts[1].strip().upper() or None if len(parts) > 1 else None,
                internal_code=parts[2].strip() or None if len(parts) > 2 else None,
                quantity=None,
                checksum_received=parts[4].strip().upper() or None if len(parts) > 4 else None,
                checksum_expected=None,
                raw_value=text,
                detail="d1_grammar_mismatch",
            )
        return ParsedProductLabelPayload(
            status=ProductLabelValidationStatus.NOT_OUR_FORMAT,
            format_version=None,
            label_id=None,
            internal_code=None,
            quantity=None,
            checksum_received=None,
            checksum_expected=None,
            raw_value=text,
            detail="not D1 product label",
        )

    label_id = match.group(1).upper()
    internal_code = match.group(2).strip()
    quantity = int(match.group(3))
    checksum_received = match.group(4).upper()
    expected = compute_product_label_checksum(
        label_id=label_id, internal_code=internal_code, quantity=quantity
    )
    normalized = build_product_label_payload(
        label_id=label_id, internal_code=internal_code, quantity=quantity
    )
    if checksum_received != expected:
        return ParsedProductLabelPayload(
            status=ProductLabelValidationStatus.CHECKSUM_FAILED,
            format_version=PRODUCT_LABEL_FORMAT_VERSION,
            label_id=label_id,
            internal_code=internal_code,
            quantity=quantity,
            checksum_received=checksum_received,
            checksum_expected=expected,
            raw_value=text,
            normalized_payload=normalized,
            detail="checksum mismatch",
        )
    return ParsedProductLabelPayload(
        status=ProductLabelValidationStatus.VALID,
        format_version=PRODUCT_LABEL_FORMAT_VERSION,
        label_id=label_id,
        internal_code=internal_code,
        quantity=quantity,
        checksum_received=checksum_received,
        checksum_expected=expected,
        raw_value=text,
        normalized_payload=normalized,
    )


__all__ = [
    "LABEL_ID_ALPHABET",
    "LABEL_ID_LENGTH",
    "PRODUCT_LABEL_FORMAT_VERSION",
    "PRODUCT_LABEL_PREFIX",
    "ParsedProductLabelPayload",
    "ProductLabelValidationStatus",
    "build_product_label_payload",
    "compute_product_label_checksum",
    "generate_product_label_id",
    "normalize_product_label_raw",
    "parse_product_label_payload",
]
