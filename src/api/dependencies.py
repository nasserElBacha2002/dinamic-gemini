"""
Central dependency provisioning for v3 API — Épica 2 + Épica 3.

Provides InventoryRepository, AisleRepository (SQL when sqlserver_enabled, else in-memory),
Clock, and use cases. Route modules depend on these; no infrastructure types in route code.

Fallback: when SQL is enabled but connection fails, behavior is controlled by
V3_ALLOW_IN_MEMORY_FALLBACK (env). If "false" / "0" / "no", fail fast (re-raise).
If "true" (default), fall back to in-memory for local/dev/test. Set to false in
production-like environments to avoid silent use of non-persistent storage.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from pathlib import Path

from fastapi import Depends

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository, SourceAssetRepository
from src.application.use_cases.create_aisle import CreateAisleUseCase
from src.application.use_cases.create_inventory import CreateInventoryUseCase
from src.application.use_cases.get_aisle_processing_status import GetAisleProcessingStatusUseCase
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.list_aisles_by_inventory import ListAislesByInventoryUseCase
from src.application.use_cases.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase
from src.application.use_cases.start_aisle_processing import StartAisleProcessingUseCase
from src.application.use_cases.upload_aisle_assets import UploadAisleAssetsUseCase

logger = logging.getLogger(__name__)

_inventory_repo: Optional[InventoryRepository] = None
_aisle_repo: Optional[AisleRepository] = None
_job_repo: Optional[JobRepository] = None
_asset_repo: Optional[SourceAssetRepository] = None
_v3_sql_client = None  # SqlServerClient when DB enabled; shared by inventory and aisle repos


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


def _get_v3_sql_client():
    """Return shared SQL client for v3 repos; verify connectivity. Cached per process. Raises on failure."""
    global _v3_sql_client
    if _v3_sql_client is not None:
        return _v3_sql_client
    from src.config import load_settings
    from src.database.sqlserver import SqlServerClient
    client = SqlServerClient(load_settings().sqlserver_connection_string)
    with client.cursor() as cur:
        cur.execute("SELECT 1")
    _v3_sql_client = client
    return _v3_sql_client


def get_inventory_repo() -> InventoryRepository:
    """Return SQL-backed repo when DB is enabled, else in-memory. Cached per process."""
    global _inventory_repo
    if _inventory_repo is not None:
        return _inventory_repo
    if _v3_db_enabled():
        try:
            client = _get_v3_sql_client()
            from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
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


def get_aisle_repo() -> AisleRepository:
    """Return SQL-backed repo when DB is enabled, else in-memory. Cached per process. Shares SQL client with inventory repo."""
    global _aisle_repo
    if _aisle_repo is not None:
        return _aisle_repo
    if _v3_db_enabled():
        try:
            client = _get_v3_sql_client()
            from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
            _aisle_repo = SqlAisleRepository(client)
            logger.info("v3 AisleRepository: using SQL backend")
        except Exception as e:
            if not _v3_allow_in_memory_fallback():
                logger.error("v3 SQL aisle repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                raise
            logger.warning("v3 SQL aisle repo init failed, falling back to in-memory: %s", e)
            from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
            _aisle_repo = MemoryAisleRepository()
    else:
        from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
        _aisle_repo = MemoryAisleRepository()
    return _aisle_repo


def get_job_repo() -> JobRepository:
    """Return SQL-backed JobRepository when DB is enabled, else in-memory. Cached per process."""
    global _job_repo
    if _job_repo is not None:
        return _job_repo
    if _v3_db_enabled():
        try:
            client = _get_v3_sql_client()
            from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
            _job_repo = SqlJobRepository(client)
            logger.info("v3 JobRepository: using SQL backend")
        except Exception as e:
            if not _v3_allow_in_memory_fallback():
                logger.error("v3 SQL job repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                raise
            logger.warning("v3 SQL job repo init failed, falling back to in-memory: %s", e)
            from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
            _job_repo = MemoryJobRepository()
    else:
        from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
        _job_repo = MemoryJobRepository()
    return _job_repo


def get_source_asset_repo() -> SourceAssetRepository:
    """Return SQL-backed SourceAssetRepository when DB is enabled, else in-memory. Cached per process."""
    global _asset_repo
    if _asset_repo is not None:
        return _asset_repo
    if _v3_db_enabled():
        try:
            client = _get_v3_sql_client()
            from src.infrastructure.repositories.sql_source_asset_repository import SqlSourceAssetRepository
            _asset_repo = SqlSourceAssetRepository(client)
            logger.info("v3 SourceAssetRepository: using SQL backend")
        except Exception as e:
            if not _v3_allow_in_memory_fallback():
                logger.error("v3 SQL source_asset repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                raise
            logger.warning("v3 SQL source_asset repo init failed, falling back to in-memory: %s", e)
            from src.infrastructure.repositories.memory_source_asset_repository import MemorySourceAssetRepository
            _asset_repo = MemorySourceAssetRepository()
    else:
        from src.infrastructure.repositories.memory_source_asset_repository import MemorySourceAssetRepository
        _asset_repo = MemorySourceAssetRepository()
    return _asset_repo


def get_artifact_storage():
    """Return v3 ArtifactStorage adapter for aisle uploads. Base path: output_dir/v3_uploads."""
    from src.config import load_settings
    from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
    base = Path(load_settings().output_dir) / "v3_uploads"
    base.mkdir(parents=True, exist_ok=True)
    return V3ArtifactStorageAdapter(base)


def get_job_queue():
    """Return v3 JobQueue adapter (enqueue(job_type, payload) -> job_id). Stateless."""
    from src.infrastructure.queue.v3_job_queue_adapter import V3JobQueueAdapter
    return V3JobQueueAdapter()


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


def get_get_inventory_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
) -> GetInventoryUseCase:
    return GetInventoryUseCase(inventory_repo=repo)


def get_create_aisle_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
) -> CreateAisleUseCase:
    return CreateAisleUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        clock=clock,
    )


def get_list_aisles_by_inventory_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
) -> ListAislesByInventoryUseCase:
    return ListAislesByInventoryUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
    )


def get_list_aisles_with_status_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> ListAislesWithStatusUseCase:
    return ListAislesWithStatusUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
    )


def get_start_aisle_processing_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    job_queue=Depends(get_job_queue),
    clock: Clock = Depends(get_clock),
) -> StartAisleProcessingUseCase:
    return StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=job_queue,
        clock=clock,
    )


def get_get_aisle_processing_status_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> GetAisleProcessingStatusUseCase:
    return GetAisleProcessingStatusUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
    )


def get_upload_aisle_assets_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
) -> UploadAisleAssetsUseCase:
    return UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=artifact_storage,
        clock=clock,
    )


def get_list_aisle_assets_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
) -> ListAisleAssetsUseCase:
    return ListAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
    )
