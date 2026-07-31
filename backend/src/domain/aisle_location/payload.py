"""Canonical DINAMIC_POSITION payload helpers — Phase 1 (no crypto)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.domain.aisle_location.label_entities import (
    POSITIONING_LABEL_PAYLOAD_VERSION,
    POSITIONING_LABEL_TYPE,
)


def build_positioning_label_payload(
    *,
    public_label_id: str,
    public_position_id: str,
    version: int = POSITIONING_LABEL_PAYLOAD_VERSION,
) -> dict[str, Any]:
    """Build the versioned discriminator payload for a positioning label."""
    return {
        "type": POSITIONING_LABEL_TYPE,
        "version": int(version),
        "label_id": public_label_id,
        "position_id": public_position_id,
    }


def canonicalize_positioning_payload(payload: dict[str, Any]) -> str:
    """Stable JSON for hashing (sorted keys, no whitespace variance)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_sha256(payload: dict[str, Any]) -> str:
    raw = canonicalize_positioning_payload(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_positioning_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    if payload.get("type") != POSITIONING_LABEL_TYPE:
        raise ValueError(f"payload.type must be {POSITIONING_LABEL_TYPE}")
    if int(payload.get("version", -1)) < 1:
        raise ValueError("payload.version must be >= 1")
    label_id = payload.get("label_id")
    position_id = payload.get("position_id")
    if not isinstance(label_id, str) or not label_id.strip():
        raise ValueError("payload.label_id is required")
    if not isinstance(position_id, str) or not position_id.strip():
        raise ValueError("payload.position_id is required")
    # Item identity must never appear on positioning payloads.
    for forbidden in ("sku", "product_id", "item_id", "quantity", "pallet_sku"):
        if forbidden in payload:
            raise ValueError(f"positioning payload must not include {forbidden}")
