#!/usr/bin/env python3
"""Deterministic MediaMTX path token for inventory + aisle code (DIN-508 POC)."""

from __future__ import annotations

import hashlib
import sys
import uuid

# dbo.aisles.code: VARCHAR(64), SQL_Latin1_General_CP1_CI_AS (DIN-508 SQL probe).
# Application: create/lookup uses code.strip() (see CreateAisleUseCase / SqlAisleRepository).
# API admits code length 1..64 (CreateAisleRequest); no extra charset filter in API.
#
# Channel identity contract (Phase 2 final):
# - inventory_id: canonical UUID string from uuid.UUID (lowercase hex + hyphens).
# - aisle code: strip; refuse if len > 64; uppercase for CI Latin aisle codes.
# - Limitation: Python .upper() may diverge from SQL for some Unicode (e.g. ß, some accents).
#   Future FastAPI grants must compare slug using the same helper OR SQL equivalence when uncertain.

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
    payload = f"{inv}\0{code}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def mediamtx_path(inventory_id: str, aisle_code: str) -> str:
    inv = normalize_inventory_id(inventory_id)
    return f"live/{inv}/{channel_slug(inv, aisle_code)}"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: channel_id.py <inventory_id> <aisle_code>", file=sys.stderr)
        return 2
    print(mediamtx_path(sys.argv[1], sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())