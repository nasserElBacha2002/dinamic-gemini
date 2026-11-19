"""Metadata persisted on CSV imports created from Raspberry scanner ZIPs."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class LocalScannerPackageImportMetadata:
    aisle_code: str
    aisle_will_be_created: bool
    client_id: str | None = None
    client_supplier_id: str | None = None
    inventory_name: str | None = None
    inventory_provisional: bool = False
    aisle_created_on_confirm: bool = False

    def to_json(self) -> str:
        payload: dict[str, object] = {
            "kind": "RASPBERRY_SCANNER_PACKAGE",
            "aisle_code": self.aisle_code,
            "aisle_will_be_created": self.aisle_will_be_created,
        }
        if self.client_id:
            payload["client_id"] = self.client_id
        if self.client_supplier_id:
            payload["client_supplier_id"] = self.client_supplier_id
        if self.inventory_name:
            payload["inventory_name"] = self.inventory_name
        if self.inventory_provisional:
            payload["inventory_provisional"] = True
        if self.aisle_created_on_confirm:
            payload["aisle_created_on_confirm"] = True
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str | None) -> LocalScannerPackageImportMetadata | None:
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or data.get("kind") != "RASPBERRY_SCANNER_PACKAGE":
            return None
        aisle_code = str(data.get("aisle_code") or "").strip()
        if not aisle_code:
            return None
        return cls(
            aisle_code=aisle_code,
            aisle_will_be_created=bool(data.get("aisle_will_be_created")),
            client_id=str(data.get("client_id") or "").strip() or None,
            client_supplier_id=str(data.get("client_supplier_id") or "").strip() or None,
            inventory_name=str(data.get("inventory_name") or "").strip() or None,
            inventory_provisional=bool(data.get("inventory_provisional")),
            aisle_created_on_confirm=bool(data.get("aisle_created_on_confirm")),
        )
