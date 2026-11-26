"""Deterministic MediaMTX path token for inventory + aisle code (DIN-508)."""

from __future__ import annotations

import hashlib
import re
import uuid

# dbo.aisles.code: VARCHAR(64), SQL_Latin1_General_CP1_CI_AS (DIN-508 SQL probe).
# Application: create/lookup uses code.strip() (see CreateAisleUseCase / SqlAisleRepository).

MAX_AISLE_CODE_LEN = 64


def normalize_inventory_id(inventory_id: str) -> str:
    raw = (inventory_id or "").strip()
    try:
        return str(uuid.UUID(raw))
    except ValueError as exc:
        raise ValueError(f"inventory_id must be a valid UUID, got {inventory_id!r}") from exc


def canonical_aisle_code_for_channel(code: str) -> str:
    """Normalize aisle code before slug derivation (strip + CI uppercase)."""
    normalized = (code or "").strip()
    if not normalized:
        raise ValueError("aisle code must be non-empty after strip")
    if len(normalized) > MAX_AISLE_CODE_LEN:
        raise ValueError(f"aisle code exceeds max length {MAX_AISLE_CODE_LEN}")
    return normalized.upper()


def channel_slug(inventory_id: str, aisle_code: str) -> str:
    inv = normalize_inventory_id(inventory_id)
    code = canonical_aisle_code_for_channel(aisle_code)
    payload = f"{inv}\0{code}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def slugify_path_segment(value: str, *, max_len: int = 48) -> str:
    """Safe MediaMTX path segment for manual entry (letters, digits, _, -)."""
    raw = (value or "").strip()
    if not raw:
        return ""
    normalized = re.sub(r"[^\w\-]+", "_", raw, flags=re.UNICODE)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        return ""
    return normalized[:max_len]


def mediamtx_path(
    inventory_id: str,
    aisle_code: str,
    *,
    inventory_name: str = "",
) -> str:
    """Human RTMP/HLS path: live/<inventory-name>/<aisle-code> (auth still required)."""
    inv = normalize_inventory_id(inventory_id)
    code = canonical_aisle_code_for_channel(aisle_code)
    inv_part = slugify_path_segment(inventory_name)
    if not inv_part:
        inv_part = slugify_path_segment(inv.replace("-", ""))[:16]
    aisle_part = slugify_path_segment(code) or slugify_path_segment(aisle_code)
    return f"live/{inv_part}/{aisle_part}"
