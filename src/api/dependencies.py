"""
Central dependency provisioning for v3 API — Épica 2.

Provides InventoryRepository (SQL when sqlserver_enabled, else in-memory), Clock,
and use cases. Route modules depend on these; no infrastructure types in route code.

Fallback: when SQL is enabled but connection fails, behavior is controlled by
V3_ALLOW_IN_MEMORY_FALLBACK (env). If "false" / "0" / "no", fail fast (re-raise).
If "true" (default), fall back to in-memory for local/dev/test. Set to false in
production-like environments to avoid silent use of non-persistent storage.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends

from src.application.ports.clock import Clock
from src.application.ports.repositories import InventoryRepository
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase

logger = logging.getLogger(__name__)

_inventory_repo: Optional[InventoryRepository] = None


def _v3_allow_in_memory_fallback() -> bool:
    """True = fall back to in-memory when SQL is enabled but connection fails (dev/test)."""
    raw = (os.getenv("V3_ALLOW_IN_MEMORY_FALLBACK") or "true").strip().lower()
    return raw in ("true", "1", "yes")


def _v3_db_enabled() -> bool:
    from src.config import load_settings
    s = load_settings()
    return bool(
        getattr(s, "sqlserver_enabled", False)
        and (getattr(s, "sqlserver_connection_string", "") or "").strip()
    )


def get_inventory_repo() -> InventoryRepository:
    """Return SQL-backed repo when DB is enabled, else in-memory. Cached per process."""
    global _inventory_repo
    if _inventory_repo is not None:
        return _inventory_repo
    if _v3_db_enabled():
        try:
            from src.config import load_settings
            from src.database.sqlserver import SqlServerClient
            from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
            client = SqlServerClient(load_settings().sqlserver_connection_string)
            # Verify connectivity before using SQL repo; fall back to memory if unreachable
            with client.cursor() as cur:
                cur.execute("SELECT 1")
            _inventory_repo = SqlInventoryRepository(client)
            logger.info("v3 InventoryRepository: using SQL backend")
        except Exception as e:
            if not _v3_allow_in_memory_fallback():
                logger.error("v3 SQL repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                raise
            logger.warning("v3 SQL repo init failed, falling back to in-memory: %s", e)
            from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
            _inventory_repo = MemoryInventoryRepository()
    else:
        from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
        _inventory_repo = MemoryInventoryRepository()
    return _inventory_repo


def get_clock() -> Clock:
    """Return UTC clock. Stateless, new instance per call."""
    from src.infrastructure.adapters.clock import UtcClock
    return UtcClock()


def get_create_inventory_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
    clock: Clock = Depends(get_clock),
) -> CreateInventoryUseCase:
    return CreateInventoryUseCase(inventory_repo=repo, clock=clock)


def get_list_inventories_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
) -> ListInventoriesUseCase:
    return ListInventoriesUseCase(inventory_repo=repo)
