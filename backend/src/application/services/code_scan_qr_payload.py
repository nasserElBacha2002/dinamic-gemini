"""QR / barcode payload extraction for exact code scan matching.

Supports:
- SKU= / barcode= key-value fragments (legacy)
- Inventory label pipe payload: internal_code|quantity
- Legacy DI1 barcode: DI1|C=<urlencoded>|Q=<qty>
- Multiline human QR with "Código interno: ..."
"""

from __future__ import annotations

import re
from urllib.parse import unquote

_SKU_PATTERN = re.compile(r"(?i)(?:^|[?&;,\s])sku\s*[=:]\s*([^\s&;,]+)")
_BARCODE_PATTERN = re.compile(r"(?i)(?:^|[?&;,\s])barcode\s*[=:]\s*([^\s&;,]+)")
_DI1_PATTERN = re.compile(r"(?i)^DI1\|C=([^|]+)\|Q=([1-9]\d{0,7})$")
_PIPE_PATTERN = re.compile(r"^([^|\n]{1,48})\|([1-9]\d{0,7})$")
_LABELED_CODE_PATTERN = re.compile(r"(?im)^\s*C[oó]digo interno:\s*(.+)\s*$")


def extract_qr_payload_lookup_values(raw: str) -> tuple[str, ...]:
    """Return additional lookup strings from known QR/barcode payload shapes."""
    text = (raw or "").strip()
    values: list[str] = []

    def add(token: str | None) -> None:
        if not token:
            return
        cleaned = token.strip()
        if cleaned and cleaned not in values:
            values.append(cleaned)

    for pattern in (_SKU_PATTERN, _BARCODE_PATTERN):
        for match in pattern.finditer(text):
            add(match.group(1))

    di1 = _DI1_PATTERN.match(text)
    if di1:
        try:
            add(unquote(di1.group(1)))
        except Exception:
            add(di1.group(1))

    pipe = _PIPE_PATTERN.match(text)
    if pipe:
        add(pipe.group(1))

    labeled = _LABELED_CODE_PATTERN.search(text)
    if labeled:
        add(labeled.group(1).split("\n")[0].strip())

    return tuple(values)


def parse_inventory_code_payload(raw: str) -> dict[str, str | int | None]:
    """Parse inventory label payload into internal_code + quantity.

    Returns quantity as int when present, otherwise None (legacy code-only).
    Raises ValueError for empty input; does not raise for plain codes.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty payload")

    di1 = _DI1_PATTERN.match(text)
    if di1:
        try:
            code = unquote(di1.group(1)).strip()
        except Exception as exc:
            raise ValueError("invalid DI1 escape") from exc
        return {"internal_code": code, "quantity": int(di1.group(2))}

    pipe = _PIPE_PATTERN.match(text)
    if pipe:
        return {"internal_code": pipe.group(1).strip(), "quantity": int(pipe.group(2))}

    labeled = _LABELED_CODE_PATTERN.search(text)
    if labeled:
        code = labeled.group(1).split("\n")[0].strip()
        if code:
            return {"internal_code": code, "quantity": None}

    # Plain code-only (or unknown structured text — best-effort first line)
    first = text.split("\n", 1)[0].strip()
    if not first:
        raise ValueError("empty payload")
    return {"internal_code": first[:48], "quantity": None}
