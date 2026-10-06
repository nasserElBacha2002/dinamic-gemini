"""Sync inventory aisle bindings from existing v3 recognition-config API."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from inventory_context import InventoryContextError, InventoryOperationalConfig


class InventoryContextSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class InventoryListEntry:
    inventory_id: str
    name: str
    client_id: str | None
    status: str


def operational_config_from_recognition_bundle(data: Any) -> InventoryOperationalConfig:
    if not isinstance(data, dict):
        raise InventoryContextSyncError("recognition-config response must be a JSON object")
    inventory_id = str(data.get("inventory_id") or "").strip()
    if not inventory_id:
        raise InventoryContextSyncError("recognition-config missing inventory_id")
    client_id = str(data.get("client_id") or "").strip() or None
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
    payload: dict[str, Any] = {"inventory_id": inventory_id, "aisles": aisles}
    if client_id:
        payload["client_id"] = client_id
    return InventoryOperationalConfig.from_dict(payload)


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
        data = self._get_json(url)
        try:
            return operational_config_from_recognition_bundle(data)
        except InventoryContextError as exc:
            raise InventoryContextSyncError(str(exc)) from exc

    def list_inventories(self, *, client_id: str | None = None) -> tuple[InventoryListEntry, ...]:
        wanted = (client_id or "").strip() or None
        items: list[InventoryListEntry] = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            query = urllib.parse.urlencode({"page": page, "page_size": 200, "sort_by": "updated_at", "sort_dir": "desc"})
            data = self._get_json(f"{self._base_url}/api/v3/inventories/?{query}")
            if not isinstance(data, dict):
                raise InventoryContextSyncError("inventory list response must be a JSON object")
            raw_items = data.get("items")
            if not isinstance(raw_items, list):
                raise InventoryContextSyncError("inventory list missing items")
            for row in raw_items:
                entry = _inventory_list_entry(row)
                if entry is None:
                    continue
                if wanted and entry.client_id and entry.client_id != wanted:
                    continue
                if wanted and not entry.client_id:
                    continue
                items.append(entry)
            raw_total_pages = data.get("total_pages")
            if isinstance(raw_total_pages, int) and raw_total_pages > 0:
                total_pages = raw_total_pages
            else:
                total_pages = page
            page += 1
            if page > 20:
                break
        return tuple(items)

    def _get_json(self, url: str) -> Any:
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
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InventoryContextSyncError("backend returned invalid JSON") from exc


def _inventory_list_entry(row: Any) -> InventoryListEntry | None:
    if not isinstance(row, dict):
        return None
    inventory_id = str(row.get("id") or "").strip()
    name = str(row.get("name") or "").strip()
    if not inventory_id:
        return None
    client_raw = row.get("client_id")
    client_id = str(client_raw).strip() if client_raw is not None else ""
    return InventoryListEntry(
        inventory_id=inventory_id,
        name=name or inventory_id,
        client_id=client_id or None,
        status=str(row.get("status") or "").strip(),
    )
