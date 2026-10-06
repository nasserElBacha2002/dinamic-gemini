"""Resolve inventory/aisle UUIDs for a captured aisle code from durable local config."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class InventoryContextError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedInventoryAisle:
    inventory_id: str
    aisle_id: str
    aisle_code: str


@dataclass(frozen=True)
class InventoryOperationalConfig:
    inventory_id: str
    aisles: tuple[tuple[str, str], ...]  # (aisle_code, aisle_id)

    @classmethod
    def from_dict(cls, data: Any) -> InventoryOperationalConfig:
        if not isinstance(data, dict):
            raise InventoryContextError(
                "INVENTORY_CONTEXT_INVALID",
                "inventory context must be a JSON object",
            )
        inventory_id = str(data.get("inventory_id") or "").strip()
        if not inventory_id:
            raise InventoryContextError(
                "INVENTORY_CONTEXT_INVALID",
                "inventory_id is required",
            )
        raw_aisles = data.get("aisles")
        if not isinstance(raw_aisles, list) or not raw_aisles:
            raise InventoryContextError(
                "INVENTORY_CONTEXT_INVALID",
                "aisles must be a non-empty array",
            )
        pairs: list[tuple[str, str]] = []
        seen_codes: set[str] = set()
        for row in raw_aisles:
            if not isinstance(row, dict):
                raise InventoryContextError(
                    "INVENTORY_CONTEXT_INVALID",
                    "aisle entry must be an object",
                )
            aisle_id = str(row.get("aisle_id") or "").strip()
            aisle_code = str(row.get("aisle_code") or "").strip()
            if not aisle_id or not aisle_code:
                raise InventoryContextError(
                    "INVENTORY_CONTEXT_INVALID",
                    "each aisle requires aisle_id and aisle_code",
                )
            normalized = aisle_code.casefold()
            if normalized in seen_codes:
                raise InventoryContextError(
                    "INVENTORY_CONTEXT_INVALID",
                    f"duplicate aisle_code in context: {aisle_code}",
                )
            seen_codes.add(normalized)
            pairs.append((aisle_code, aisle_id))
        return cls(inventory_id=inventory_id, aisles=tuple(pairs))

    def resolve_aisle(self, aisle_code: str) -> ResolvedInventoryAisle:
        target = aisle_code.strip()
        if not target:
            raise InventoryContextError("AISLE_CODE_REQUIRED", "aisle_code is required")
        for code, aisle_id in self.aisles:
            if code == target:
                return ResolvedInventoryAisle(
                    inventory_id=self.inventory_id,
                    aisle_id=aisle_id,
                    aisle_code=code,
                )
        raise InventoryContextError(
            "AISLE_NOT_IN_INVENTORY_CONTEXT",
            f"aisle_code {target!r} is not configured for inventory {self.inventory_id}",
        )


def default_export_directory() -> Path:
    return Path(
        os.environ.get(
            "DINAMIC_EXPORT_DIRECTORY",
            "/var/lib/dinamic-raspberry-scanner/exports",
        )
    )


def inventory_context_path() -> Path:
    """Durable inventory context file; override with DINAMIC_INVENTORY_CONTEXT_PATH."""
    raw = (
        os.environ.get("DINAMIC_INVENTORY_CONTEXT_PATH")
        or os.environ.get("DINAMIC_INVENTORY_CONFIG_PATH")
        or ""
    ).strip()
    if raw:
        return Path(raw)
    return default_export_directory().parent / "inventory-context.json"


def inventory_context_path_from_environment() -> Path:
    """Alias for :func:`inventory_context_path` (default path under local storage)."""
    return inventory_context_path()


def _inventory_sync_env_configured() -> bool:
    inventory_id = (os.environ.get("DINAMIC_INVENTORY_ID") or "").strip()
    base_url = (os.environ.get("DINAMIC_BACKEND_URL") or "").strip()
    bearer = (
        os.environ.get("DINAMIC_BACKEND_BEARER_TOKEN")
        or os.environ.get("DINAMIC_BACKEND_TOKEN")
        or ""
    ).strip()
    return bool(inventory_id and base_url and bearer)


def load_inventory_operational_config(path: Path | None = None) -> InventoryOperationalConfig:
    from config.inventory_context_repository import InventoryContextRepository

    config_path = path or inventory_context_path()
    repo = InventoryContextRepository(config_path)
    config = repo.load()
    if config is None and path is None and _inventory_sync_env_configured():
        sync_inventory_context_from_backend()
        config = repo.load()
    if config is None:
        raise InventoryContextError(
            "INVENTORY_CONTEXT_NOT_FOUND",
            f"inventory context file not found: {config_path}",
        )
    return config


def resolve_inventory_aisle_for_capture(
    aisle_code: str,
    *,
    config: InventoryOperationalConfig | None = None,
) -> ResolvedInventoryAisle:
    operational = config or load_inventory_operational_config()
    return operational.resolve_aisle(aisle_code)


def sync_inventory_context_from_backend() -> InventoryOperationalConfig:
    """Fetch aisle bindings from v3 recognition-config and persist locally."""
    import os

    from config.inventory_context_repository import InventoryContextRepository
    from config.inventory_context_sync import (
        InventoryContextBackendClient,
        InventoryContextSyncError,
    )

    inventory_id = (os.environ.get("DINAMIC_INVENTORY_ID") or "").strip()
    base_url = (os.environ.get("DINAMIC_BACKEND_URL") or "").strip()
    bearer = (
        os.environ.get("DINAMIC_BACKEND_BEARER_TOKEN")
        or os.environ.get("DINAMIC_BACKEND_TOKEN")
        or ""
    ).strip()
    if not inventory_id or not base_url or not bearer:
        raise InventoryContextError(
            "INVENTORY_CONTEXT_SYNC_NOT_CONFIGURED",
            "DINAMIC_INVENTORY_ID, DINAMIC_BACKEND_URL and DINAMIC_BACKEND_BEARER_TOKEN are required",
        )
    path = inventory_context_path()
    client = InventoryContextBackendClient(base_url, bearer)
    try:
        config = client.fetch_operational_config(inventory_id)
    except InventoryContextSyncError as exc:
        raise InventoryContextError("INVENTORY_CONTEXT_SYNC_FAILED", str(exc)) from exc
    InventoryContextRepository(path).save(config)
    return config
