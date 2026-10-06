"""Sync inventory aisle bindings from existing v3 recognition-config API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from inventory_context import InventoryContextError, InventoryOperationalConfig


class InventoryContextSyncError(RuntimeError):
    pass


def operational_config_from_recognition_bundle(data: Any) -> InventoryOperationalConfig:
    if not isinstance(data, dict):
        raise InventoryContextSyncError("recognition-config response must be a JSON object")
    inventory_id = str(data.get("inventory_id") or "").strip()
    if not inventory_id:
        raise InventoryContextSyncError("recognition-config missing inventory_id")
    raw_aisles = data.get("aisles")
    if not isinstance(raw_aisles, list) or not raw_aisles:
        raise InventoryContextSyncError("recognition-config missing aisles")
    aisles: list[dict[str, str]] = []
    for row in raw_aisles:
        if not isinstance(row, dict):
            continue
        aisle_id = str(row.get("aisle_id") or "").strip()
        aisle_code = str(row.get("aisle_code") or "").strip()
        if aisle_id and aisle_code:
            aisles.append({"aisle_id": aisle_id, "aisle_code": aisle_code})
    if not aisles:
        raise InventoryContextSyncError("recognition-config has no aisle_id/aisle_code rows")
    return InventoryOperationalConfig.from_dict(
        {"inventory_id": inventory_id, "aisles": aisles}
    )


class InventoryContextBackendClient:
    def __init__(
        self,
        base_url: str,
        bearer_token: str,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token.strip()
        self._timeout_seconds = timeout_seconds

    def fetch_operational_config(self, inventory_id: str) -> InventoryOperationalConfig:
        url = (
            f"{self._base_url}/api/v3/inventories/"
            f"{urllib.parse.quote(inventory_id, safe='')}/recognition-config"
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._bearer_token}",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise InventoryContextSyncError(f"backend returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise InventoryContextSyncError(f"backend unavailable: {exc}") from exc
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InventoryContextSyncError("backend returned invalid JSON") from exc
        try:
            return operational_config_from_recognition_bundle(data)
        except InventoryContextError as exc:
            raise InventoryContextSyncError(str(exc)) from exc


import urllib.parse  # noqa: E402
