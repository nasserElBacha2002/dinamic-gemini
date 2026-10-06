"""Resolve inventory/aisle UUIDs for a captured aisle code from durable local config."""

from __future__ import annotations

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
    client_id: str | None = None

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
        client_raw = data.get("client_id")
        client_id = str(client_raw).strip() if client_raw is not None else ""
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
        return cls(
            inventory_id=inventory_id,
            aisles=tuple(pairs),
            client_id=client_id or None,
        )

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


def _backend_sync_credentials() -> tuple[str, str] | None:
    base_url = (os.environ.get("DINAMIC_BACKEND_URL") or "").strip()
    bearer = (
        os.environ.get("DINAMIC_BACKEND_BEARER_TOKEN")
        or os.environ.get("DINAMIC_BACKEND_TOKEN")
        or ""
    ).strip()
    if base_url and bearer:
        return base_url, bearer
    return None


def _optional_env_inventory_id() -> str | None:
    inventory_id = (os.environ.get("DINAMIC_INVENTORY_ID") or "").strip()
    return inventory_id or None


def _cached_config_usable(
    cached: InventoryOperationalConfig | None,
    *,
    inventory_id: str | None,
    client_id: str | None,
) -> bool:
    if cached is None:
        return False
    if inventory_id and cached.inventory_id != inventory_id:
        return False
    if client_id and cached.client_id and cached.client_id != client_id:
        return False
    return True


def _offline_unavailable_error(*, had_unusable_cache: bool) -> InventoryContextError:
    if had_unusable_cache:
        return InventoryContextError(
            "INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE",
            "el contexto cacheado no corresponde al inventario o cliente "
            "seleccionado y no hay conexión para sincronizar uno nuevo",
        )
    return InventoryContextError(
        "INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE",
        "no hay contexto de inventario disponible offline; "
        "sincronizá un inventario estando en línea antes de operar sin conexión",
    )


def peek_inventory_operational_config(
    path: Path | None = None,
) -> InventoryOperationalConfig | None:
    """Return cached context without syncing. None if the file is absent."""
    from config.inventory_context_repository import InventoryContextRepository

    return InventoryContextRepository(path or inventory_context_path()).load()


def inventory_context_status() -> dict[str, object]:
    try:
        cached = peek_inventory_operational_config()
    except InventoryContextError as exc:
        return {
            "available": False,
            "inventory_id": None,
            "client_id": None,
            "aisle_count": 0,
            "error": exc.code,
            "message": str(exc),
        }
    if cached is None:
        return {
            "available": False,
            "inventory_id": None,
            "client_id": None,
            "aisle_count": 0,
        }
    return {
        "available": True,
        "inventory_id": cached.inventory_id,
        "client_id": cached.client_id,
        "aisle_count": len(cached.aisles),
    }


def load_inventory_operational_config(
    path: Path | None = None,
    *,
    inventory_id: str | None = None,
    client_id: str | None = None,
) -> InventoryOperationalConfig:
    from config.inventory_context_repository import InventoryContextRepository

    config_path = path or inventory_context_path()
    repo = InventoryContextRepository(config_path)
    cached = repo.load()
    requested_id = (inventory_id or "").strip() or None
    requested_client = (client_id or "").strip() or None

    if path is not None:
        if cached is None:
            raise InventoryContextError(
                "INVENTORY_CONTEXT_NOT_FOUND",
                f"inventory context file not found: {config_path}",
            )
        if not _cached_config_usable(
            cached, inventory_id=requested_id, client_id=requested_client
        ):
            raise InventoryContextError(
                "INVENTORY_CONTEXT_MISMATCH",
                "explicit inventory context does not match the requested inventory",
            )
        return cached

    cached_usable = _cached_config_usable(
        cached, inventory_id=requested_id, client_id=requested_client
    )
    credentials = _backend_sync_credentials()
    target_id = requested_id
    if target_id is None and cached_usable and cached is not None:
        target_id = cached.inventory_id
    if target_id is None:
        target_id = _optional_env_inventory_id()

    if credentials is not None and target_id:
        try:
            return sync_inventory_context_from_backend(
                inventory_id=target_id,
                expected_client_id=requested_client,
            )
        except InventoryContextError:
            if cached_usable and cached is not None:
                return cached
            raise

    if cached_usable and cached is not None:
        return cached

    if credentials is None:
        raise _offline_unavailable_error(had_unusable_cache=cached is not None)

    raise InventoryContextError(
        "INVENTORY_SELECTION_REQUIRED",
        "seleccioná un inventario para sincronizar el contexto local",
    )


def resolve_inventory_aisle_for_capture(
    aisle_code: str,
    *,
    config: InventoryOperationalConfig | None = None,
    inventory_id: str | None = None,
    client_id: str | None = None,
) -> ResolvedInventoryAisle:
    operational = config or load_inventory_operational_config(
        inventory_id=inventory_id,
        client_id=client_id,
    )
    return operational.resolve_aisle(aisle_code)


def sync_inventory_context_from_backend(
    inventory_id: str | None = None,
    *,
    expected_client_id: str | None = None,
) -> InventoryOperationalConfig:
    """Fetch aisle bindings from v3 recognition-config and persist locally as cache."""
    from config.inventory_context_repository import InventoryContextRepository
    from config.inventory_context_sync import (
        InventoryContextBackendClient,
        InventoryContextSyncError,
    )

    credentials = _backend_sync_credentials()
    if credentials is None:
        raise InventoryContextError(
            "INVENTORY_CONTEXT_SYNC_NOT_CONFIGURED",
            "DINAMIC_BACKEND_URL and DINAMIC_BACKEND_BEARER_TOKEN are required",
        )
    base_url, bearer = credentials
    target = (inventory_id or "").strip()
    if not target:
        cached = peek_inventory_operational_config()
        if cached is not None:
            target = cached.inventory_id
    if not target:
        target = _optional_env_inventory_id() or ""
    if not target:
        raise InventoryContextError(
            "INVENTORY_CONTEXT_SYNC_NOT_CONFIGURED",
            "inventory_id is required to sync inventory context",
        )
    client = InventoryContextBackendClient(base_url, bearer)
    try:
        config = client.fetch_operational_config(target)
    except InventoryContextSyncError as exc:
        raise InventoryContextError("INVENTORY_CONTEXT_SYNC_FAILED", str(exc)) from exc
    expected = (expected_client_id or "").strip()
    if expected and config.client_id and config.client_id != expected:
        raise InventoryContextError(
            "INVENTORY_CLIENT_MISMATCH",
            "el inventario sincronizado no pertenece al cliente seleccionado",
        )
    InventoryContextRepository(inventory_context_path()).save(config)
    return config
