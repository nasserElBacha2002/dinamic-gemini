"""Local inventory list + per-inventory aisle context for offline operation."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.inventory_context_sync import InventoryListEntry
from durable_io import fsync_directory
from inventory_context import InventoryContextError, InventoryOperationalConfig


CATALOG_SCHEMA_VERSION = 1


class InventoryCatalogError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class InventoryCatalogEntry:
    inventory_id: str
    name: str
    client_id: str
    status: str

    @classmethod
    def from_dict(cls, data: Any) -> InventoryCatalogEntry:
        if not isinstance(data, dict):
            raise InventoryCatalogError(
                "CATALOG_INVALID",
                "inventory entry must be an object",
            )
        inventory_id = str(data.get("id") or data.get("inventory_id") or "").strip()
        name = str(data.get("name") or "").strip()
        client_id = str(data.get("client_id") or "").strip()
        status = str(data.get("status") or "imported").strip()
        if not inventory_id or not client_id:
            raise InventoryCatalogError(
                "CATALOG_INVALID",
                "inventory requires id and client_id",
            )
        return cls(
            inventory_id=inventory_id,
            name=name or inventory_id,
            client_id=client_id,
            status=status or "imported",
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.inventory_id,
            "name": self.name,
            "client_id": self.client_id,
            "status": self.status,
        }


@dataclass
class InventoryCatalogDocument:
    catalog_schema_version: int
    inventories: dict[str, InventoryCatalogEntry]
    contexts: dict[str, InventoryOperationalConfig]

    @classmethod
    def empty(cls) -> InventoryCatalogDocument:
        return cls(
            catalog_schema_version=CATALOG_SCHEMA_VERSION,
            inventories={},
            contexts={},
        )

    @classmethod
    def from_dict(cls, data: Any) -> InventoryCatalogDocument:
        if not isinstance(data, dict):
            raise InventoryCatalogError(
                "CATALOG_INVALID",
                "catalog document must be an object",
            )
        version = data.get("catalog_schema_version")
        if version != CATALOG_SCHEMA_VERSION:
            raise InventoryCatalogError(
                "CATALOG_UNSUPPORTED_SCHEMA",
                f"unsupported catalog_schema_version: {version}",
            )
        raw_inventories = data.get("inventories")
        raw_contexts = data.get("contexts")
        if not isinstance(raw_inventories, dict):
            raise InventoryCatalogError(
                "CATALOG_INVALID",
                "inventories must be an object",
            )
        if not isinstance(raw_contexts, dict):
            raise InventoryCatalogError(
                "CATALOG_INVALID",
                "contexts must be an object",
            )
        inventories: dict[str, InventoryCatalogEntry] = {}
        for key, row in raw_inventories.items():
            entry = InventoryCatalogEntry.from_dict(row)
            inventories[entry.inventory_id] = entry
        contexts: dict[str, InventoryOperationalConfig] = {}
        for inventory_id, row in raw_contexts.items():
            try:
                config = InventoryOperationalConfig.from_dict(row)
            except InventoryContextError as exc:
                raise InventoryCatalogError(exc.code, str(exc)) from exc
            contexts[str(inventory_id).strip()] = config
        return cls(
            catalog_schema_version=CATALOG_SCHEMA_VERSION,
            inventories=inventories,
            contexts=contexts,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "catalog_schema_version": self.catalog_schema_version,
            "inventories": {
                key: entry.as_dict()
                for key, entry in sorted(self.inventories.items())
            },
            "contexts": {
                key: _context_as_dict(config)
                for key, config in sorted(self.contexts.items())
            },
        }


def _context_as_dict(config: InventoryOperationalConfig) -> dict[str, object]:
    body: dict[str, object] = {
        "inventory_id": config.inventory_id,
        "aisles": [
            {"aisle_id": aisle_id, "aisle_code": aisle_code}
            for aisle_code, aisle_id in config.aisles
        ],
    }
    if config.client_id:
        body["client_id"] = config.client_id
    return body


def default_catalog_path() -> Path:
    raw = (os.environ.get("DINAMIC_INVENTORY_CATALOG_PATH") or "").strip()
    if raw:
        return Path(raw)
    from inventory_context import default_export_directory

    return default_export_directory().parent / "inventory-catalog.json"


class InventoryCatalogRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> InventoryCatalogDocument:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return InventoryCatalogDocument.empty()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InventoryCatalogError(
                "CATALOG_UNREADABLE",
                f"invalid catalog JSON: {exc}",
            ) from exc
        return InventoryCatalogDocument.from_dict(data)

    def save(self, document: InventoryCatalogDocument) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            document.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            dir=self._path.parent,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._path)
            fsync_directory(self._path.parent)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def list_for_client(self, client_id: str) -> tuple[InventoryListEntry, ...]:
        wanted = (client_id or "").strip()
        if not wanted:
            return ()
        document = self.load()
        items = [
            InventoryListEntry(
                inventory_id=entry.inventory_id,
                name=entry.name,
                client_id=entry.client_id,
                status=entry.status,
            )
            for entry in document.inventories.values()
            if entry.client_id == wanted
        ]
        return tuple(sorted(items, key=lambda row: row.name.casefold()))


def merge_catalog_documents(
    base: InventoryCatalogDocument,
    incoming: InventoryCatalogDocument,
) -> tuple[InventoryCatalogDocument, dict[str, int]]:
    inventories = dict(base.inventories)
    contexts = dict(base.contexts)
    stats = {
        "inventories_added": 0,
        "inventories_updated": 0,
        "contexts_added": 0,
        "contexts_updated": 0,
    }
    for entry in incoming.inventories.values():
        if entry.inventory_id in inventories:
            stats["inventories_updated"] += 1
        else:
            stats["inventories_added"] += 1
        inventories[entry.inventory_id] = entry
    for inventory_id, config in incoming.contexts.items():
        if inventory_id in contexts:
            stats["contexts_updated"] += 1
        else:
            stats["contexts_added"] += 1
        contexts[inventory_id] = config
    merged = InventoryCatalogDocument(
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
        inventories=inventories,
        contexts=contexts,
    )
    return merged, stats
