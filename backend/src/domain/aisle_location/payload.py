"""Canonical DINAMIC_POSITION payload helpers — Phase 2 adds HMAC fields."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.domain.aisle_location.label_entities import (
    POSITIONING_LABEL_PAYLOAD_VERSION,
    POSITIONING_LABEL_PAYLOAD_VERSION_V2,
    POSITIONING_LABEL_TYPE,
)
from src.domain.client_position_label.hierarchy import PositionHierarchy, PositionSide

_SIGNING_EXCLUDED_KEYS = frozenset({"signature"})
_HIERARCHY_KEYS = ("pallet", "side", "level", "marker_index", "marker_total")


def build_positioning_label_payload(
    *,
    public_label_id: str,
    public_position_id: str | None = None,
    version: int = POSITIONING_LABEL_PAYLOAD_VERSION,
    key_version: int | None = None,
    signature: str | None = None,
    pallet: str | None = None,
    side: str | PositionSide | None = None,
    level: int | None = None,
    marker_index: int | None = None,
    marker_total: int | None = None,
) -> dict[str, Any]:
    """Build the versioned discriminator payload for a positioning label.

    Client-scoped labels use ``label_id`` only. Legacy aisle-scoped labels may
    still carry ``position_id`` (public location id). When hierarchy fields are
    provided, payload version is set to V2 and hierarchy keys are included.
    """
    hierarchy_present = any(
        v is not None for v in (pallet, side, level, marker_index, marker_total)
    )
    resolved_version = int(version)
    if hierarchy_present:
        hierarchy = PositionHierarchy(
            pallet=str(pallet or ""),
            side=side if isinstance(side, PositionSide) else PositionSide(str(side).strip().upper()),
            level=int(level) if level is not None else 0,
            marker_index=int(marker_index) if marker_index is not None else 0,
            marker_total=int(marker_total) if marker_total is not None else 0,
        )
        resolved_version = max(resolved_version, POSITIONING_LABEL_PAYLOAD_VERSION_V2)

    payload: dict[str, Any] = {
        "type": POSITIONING_LABEL_TYPE,
        "version": resolved_version,
        "label_id": public_label_id,
    }
    if public_position_id is not None and str(public_position_id).strip():
        payload["position_id"] = str(public_position_id).strip()
    if hierarchy_present:
        payload["pallet"] = hierarchy.pallet
        payload["side"] = hierarchy.side.value
        payload["level"] = hierarchy.level
        payload["marker_index"] = hierarchy.marker_index
        payload["marker_total"] = hierarchy.marker_total
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


def _validate_hierarchy_fields(payload: dict[str, Any]) -> None:
    missing = [key for key in _HIERARCHY_KEYS if key not in payload]
    if missing:
        raise ValueError(
            "payload version >= 2 requires hierarchy fields: " + ", ".join(missing)
        )
    pallet = payload.get("pallet")
    if not isinstance(pallet, str) or not pallet.strip():
        raise ValueError("payload.pallet must be a non-empty string")
    side_raw = payload.get("side")
    if not isinstance(side_raw, str) or side_raw.strip().upper() not in (
        PositionSide.LEFT.value,
        PositionSide.RIGHT.value,
    ):
        raise ValueError("payload.side must be LEFT or RIGHT")
    try:
        level = int(payload["level"])
        marker_index = int(payload["marker_index"])
        marker_total = int(payload["marker_total"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "payload.level, marker_index, and marker_total must be integers"
        ) from exc
    # Reuse VO validation rules.
    PositionHierarchy(
        pallet=pallet,
        side=PositionSide(side_raw.strip().upper()),
        level=level,
        marker_index=marker_index,
        marker_total=marker_total,
    )


def validate_positioning_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    if payload.get("type") != POSITIONING_LABEL_TYPE:
        raise ValueError(f"payload.type must be {POSITIONING_LABEL_TYPE}")
    try:
        version = int(payload.get("version", -1))
    except (TypeError, ValueError) as exc:
        raise ValueError("payload.version must be an integer >= 1") from exc
    if version < 1:
        raise ValueError("payload.version must be >= 1")
    label_id = payload.get("label_id")
    if not isinstance(label_id, str) or not label_id.strip():
        raise ValueError("payload.label_id is required")
    if "position_id" in payload:
        position_id = payload.get("position_id")
        if not isinstance(position_id, str) or not position_id.strip():
            raise ValueError("payload.position_id must be a non-empty string when present")
    if version >= POSITIONING_LABEL_PAYLOAD_VERSION_V2:
        _validate_hierarchy_fields(payload)
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
