"""Minimal QR payload key=value extraction for exact code scan matching."""

from __future__ import annotations

import re

_SKU_PATTERN = re.compile(r"(?i)(?:^|[?&;,\s])sku\s*[=:]\s*([^\s&;,]+)")
_BARCODE_PATTERN = re.compile(r"(?i)(?:^|[?&;,\s])barcode\s*[=:]\s*([^\s&;,]+)")


def extract_qr_payload_lookup_values(raw: str) -> tuple[str, ...]:
    """Return additional lookup strings from simple SKU=/barcode= QR payloads."""
    text = raw or ""
    values: list[str] = []
    for pattern in (_SKU_PATTERN, _BARCODE_PATTERN):
        for match in pattern.finditer(text):
            token = (match.group(1) or "").strip()
            if token and token not in values:
                values.append(token)
    return tuple(values)
