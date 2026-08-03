"""Canonical DINAMIC_POSITION payload helpers — Phase 2 adds HMAC fields."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.domain.aisle_location.label_entities import (
    POSITIONING_LABEL_PAYLOAD_VERSION,
    POSITIONING_LABEL_TYPE,
)

_SIGNING_EXCLUDED_KEYS = frozenset({"signature"})


def build_positioning_label_payload(
    *,
    public_label_id: str,
    public_position_id: str | None = None,
    version: int = POSITIONING_LABEL_PAYLOAD_VERSION,
    key_version: int | None = None,
    signature: str | None = None,
) -> dict[str, Any]:
    """Build the versioned discriminator payload for a positioning label.

    Client-scoped labels use ``label_id`` only. Legacy aisle-scoped labels may
    still carry ``position_id`` (public location id).
    """
    payload: dict[str, Any] = {
        "type": POSITIONING_LABEL_TYPE,
        "version": int(version),
        "label_id": public_label_id,
    }
    if public_position_id is not None and str(public_position_id).strip():
        payload["position_id"] = str(public_position_id).strip()
    if key_version is not None:
        payload["key_version"] = int(key_version)
    if signature is not None:
        payload["signature"] = signature
    return payload


def canonicalize_positioning_payload(payload: dict[str, Any]) -> str:
    """Stable JSON for hashing/encoding (sorted keys, no whitespace variance)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonicalize_positioning_payload_for_signing(payload: dict[str, Any]) -> str:
    """Canonical UTF-8 JSON excluding the signature field (signing input)."""
    filtered = {k: v for k, v in payload.items() if k not in _SIGNING_EXCLUDED_KEYS}
    return canonicalize_positioning_payload(filtered)


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
    if not isinstance(label_id, str) or not label_id.strip():
        raise ValueError("payload.label_id is required")
    if "position_id" in payload:
        position_id = payload.get("position_id")
        if not isinstance(position_id, str) or not position_id.strip():
            raise ValueError("payload.position_id must be a non-empty string when present")
    if "key_version" in payload:
        try:
            if int(payload["key_version"]) < 1:
                raise ValueError("payload.key_version must be >= 1")
        except (TypeError, ValueError) as exc:
            raise ValueError("payload.key_version must be an integer >= 1") from exc
    if "signature" in payload:
        sig = payload.get("signature")
        if not isinstance(sig, str) or not sig.strip():
            raise ValueError("payload.signature must be a non-empty string when present")
    for forbidden in (
        "sku",
        "product_id",
        "item_id",
        "quantity",
        "pallet_sku",
        "inventory_id",
        "aisle_id",
        "job_id",
        "session_id",
    ):
        if forbidden in payload:
            raise ValueError(f"positioning payload must not include {forbidden}")
