"""Persisted scan semantics for local CSV export (aligned with mobile supplier snapshots)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


def is_likely_raw_segmented_payload(value: str) -> bool:
    text = value.strip()
    if "|" not in text:
        return False
    return len(text.split("|")) >= 3


@dataclass(frozen=True)
class ScanSemantics:
    classification: str
    selection_mode: str
    raw_payload: str
    export_line: str
    client_id: str | None
    supplier_id: str | None
    item_source: str | None
    position_source: str | None
    recognition_snapshot_json: str | None
    duplicate_label: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "selection_mode": self.selection_mode,
            "raw_payload": self.raw_payload,
            "export_line": self.export_line,
            "client_id": self.client_id,
            "supplier_id": self.supplier_id,
            "item_source": self.item_source,
            "position_source": self.position_source,
            "recognition_snapshot_json": self.recognition_snapshot_json,
            "duplicate_label": self.duplicate_label,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ScanSemantics | None:
        if not raw:
            return None
        return cls(
            classification=str(raw.get("classification") or ""),
            selection_mode=str(raw.get("selection_mode") or ""),
            raw_payload=str(raw.get("raw_payload") or ""),
            export_line=str(raw.get("export_line") or ""),
            client_id=raw.get("client_id"),
            supplier_id=raw.get("supplier_id"),
            item_source=raw.get("item_source"),
            position_source=raw.get("position_source"),
            recognition_snapshot_json=raw.get("recognition_snapshot_json"),
            duplicate_label=bool(raw.get("duplicate_label")),
        )


def build_recognition_snapshot_json(
    *,
    client_supplier_id: str | None,
    item: dict[str, object] | None,
    position: dict[str, object] | None,
) -> str | None:
    if item is None and position is None:
        return None
    payload: dict[str, Any] = {}
    if client_supplier_id:
        payload["client_supplier_id"] = client_supplier_id
    if item is not None:
        payload["item"] = item
    if position is not None:
        payload["position"] = position
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def build_scan_semantics(
    raw_value: str,
    decision: dict[str, object],
    *,
    export_line: str,
) -> ScanSemantics | None:
    if decision.get("accepted") is not True:
        return None
    recognition = decision.get("recognition")
    if not isinstance(recognition, dict):
        return None
    classification = str(decision.get("classification") or "")
    selection_mode = str(recognition.get("selection_mode") or "")
    client_id = recognition.get("client_id")
    supplier_id = recognition.get("supplier_id")
    item_source = recognition.get("item_source")
    position_source = recognition.get("position_source")
    results = recognition.get("results")
    results_dict = results if isinstance(results, dict) else {}

    item_branch: dict[str, object] | None = None
    position_branch: dict[str, object] | None = None
    client_supplier_id = str(supplier_id) if isinstance(supplier_id, str) else None

    if classification == "RAW" and selection_mode == "ALL":
        return ScanSemantics(
            classification=classification,
            selection_mode=selection_mode,
            raw_payload=raw_value,
            export_line=export_line,
            client_id=str(client_id) if isinstance(client_id, str) else None,
            supplier_id=client_supplier_id,
            item_source=str(item_source) if isinstance(item_source, str) else None,
            position_source=str(position_source) if isinstance(position_source, str) else None,
            recognition_snapshot_json=None,
        )

    if classification == "ITEM":
        item = results_dict.get("ITEM")
        if isinstance(item, dict) and item.get("status") == "VALID":
            item_branch = {
                "status": "VALID",
                "label_id": item.get("label_id"),
                "sku": item.get("sku") or item.get("internal_code"),
                "quantity": item.get("quantity"),
                "profile_id": item.get("profile_id"),
                "profile_version": item.get("profile_version"),
            }
    elif classification == "POSITION":
        position = results_dict.get("POSITION")
        if isinstance(position, dict) and position.get("status") == "VALID":
            position_branch = {
                "status": "VALID",
                "position_id": position.get("position_id"),
                "pallet": position.get("pallet"),
                "side": position.get("side"),
                "level": position.get("level"),
                "profile_id": position.get("profile_id"),
                "profile_version": position.get("profile_version"),
            }

    snapshot = build_recognition_snapshot_json(
        client_supplier_id=client_supplier_id,
        item=item_branch,
        position=position_branch,
    )
    return ScanSemantics(
        classification=classification,
        selection_mode=selection_mode,
        raw_payload=raw_value,
        export_line=export_line,
        client_id=str(client_id) if isinstance(client_id, str) else None,
        supplier_id=client_supplier_id,
        item_source=str(item_source) if isinstance(item_source, str) else None,
        position_source=str(position_source) if isinstance(position_source, str) else None,
        recognition_snapshot_json=snapshot,
    )


def products_from_snapshot(snapshot_json: str | None) -> list[dict[str, object]]:
    if not snapshot_json:
        return []
    try:
        parsed = json.loads(snapshot_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    item = parsed.get("item")
    if not isinstance(item, dict) or item.get("status") != "VALID":
        return []
    label_id = str(item.get("label_id") or "").strip()
    sku = str(item.get("sku") or item.get("internal_code") or "").strip()
    qty = item.get("quantity")
    quantity = int(qty) if isinstance(qty, int) else None
    if not label_id and not sku:
        return []
    return [
        {
            "label_id": label_id or sku,
            "internal_code": sku or None,
            "quantity": quantity,
        }
    ]


def position_from_snapshot(snapshot_json: str | None) -> dict[str, str] | None:
    if not snapshot_json:
        return None
    try:
        parsed = json.loads(snapshot_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    position = parsed.get("position")
    if not isinstance(position, dict) or position.get("status") != "VALID":
        return None
    position_id = str(position.get("position_id") or "").strip()
    if not position_id:
        return None
    pallet = str(position.get("pallet") or "").strip()
    side = str(position.get("side") or "").strip().upper()
    level = str(position.get("level") or "").strip()
    raw_payload = "|".join(part for part in (position_id, pallet, side, level) if part)
    return {
        "position_code": position_id,
        "position_label_id": position_id,
        "position_payload_raw": raw_payload if "|" in raw_payload else position_id,
        "pallet": pallet,
        "side": side,
    }


def legacy_semantics_from_photo(photo: Any) -> ScanSemantics:
    """Backward-compatible semantics for sessions saved before scan_semantics existed."""
    line = photo.export_line
    classification = "POSITION" if line.startswith("POSITION|") else "ITEM"
    return ScanSemantics(
        classification=classification,
        selection_mode="LEGACY",
        raw_payload=line,
        export_line=line,
        client_id=None,
        supplier_id=None,
        item_source=None,
        position_source=None,
        recognition_snapshot_json=None,
    )


def semantics_for_photo(photo: Any) -> ScanSemantics:
    raw = getattr(photo, "scan_semantics", None)
    if isinstance(raw, dict):
        parsed = ScanSemantics.from_dict(raw)
        if parsed is not None:
            return parsed
    return legacy_semantics_from_photo(photo)
