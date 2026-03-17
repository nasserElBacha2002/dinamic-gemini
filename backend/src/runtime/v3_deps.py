"""
Shared v3 dependency getters — used by API (via Depends) and worker.

No FastAPI dependency; neutral runtime wiring for repos and clock.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    FinalCountRepository,
    InventoryRepository,
    JobRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    ReviewActionRepository,
    SourceAssetRepository,
)
from src.application.ports.services import MetricsCalculator

logger = logging.getLogger(__name__)

_inventory_repo: Optional[InventoryRepository] = None
_aisle_repo: Optional[AisleRepository] = None
_job_repo: Optional[JobRepository] = None
_asset_repo: Optional[SourceAssetRepository] = None
_position_repo: Optional[PositionRepository] = None
_product_record_repo: Optional[ProductRecordRepository] = None
_evidence_repo: Optional[EvidenceRepository] = None
_review_action_repo: Optional[ReviewActionRepository] = None
_metrics_calculator: Optional[MetricsCalculator] = None
_raw_label_repo: Optional[RawLabelRepository] = None
_normalized_label_repo: Optional[NormalizedLabelRepository] = None
_final_count_repo: Optional[FinalCountRepository] = None
_v3_sql_client = None


def _v3_allow_in_memory_fallback() -> bool:
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


def get_position_repo() -> PositionRepository:
    global _position_repo
    if _position_repo is not None:
        return _position_repo
    if _v3_db_enabled():
        try:
            client = _get_v3_sql_client()
            from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
            _position_repo = SqlPositionRepository(client)
            logger.info("v3 PositionRepository: using SQL backend")
        except Exception as e:
            if not _v3_allow_in_memory_fallback():
                logger.error("v3 SQL position repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                raise
            logger.warning("v3 SQL position repo init failed, falling back to in-memory: %s", e)
            from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
            _position_repo = MemoryPositionRepository()
    else:
        from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
        _position_repo = MemoryPositionRepository()
    return _position_repo


def get_product_record_repo() -> ProductRecordRepository:
    global _product_record_repo
    if _product_record_repo is not None:
        return _product_record_repo
    if _v3_db_enabled():
        try:
            client = _get_v3_sql_client()
            from src.infrastructure.repositories.sql_product_record_repository import SqlProductRecordRepository
            _product_record_repo = SqlProductRecordRepository(client)
            logger.info("v3 ProductRecordRepository: using SQL backend")
        except Exception as e:
            if not _v3_allow_in_memory_fallback():
                logger.error("v3 SQL product_record repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                raise
            logger.warning("v3 SQL product_record repo init failed, falling back to in-memory: %s", e)
            from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository
            _product_record_repo = MemoryProductRecordRepository()
    else:
        from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository
        _product_record_repo = MemoryProductRecordRepository()
    return _product_record_repo


def get_evidence_repo() -> EvidenceRepository:
    global _evidence_repo
    if _evidence_repo is not None:
        return _evidence_repo
    if _v3_db_enabled():
        try:
            client = _get_v3_sql_client()
            from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository
            _evidence_repo = SqlEvidenceRepository(client)
            logger.info("v3 EvidenceRepository: using SQL backend")
        except Exception as e:
            if not _v3_allow_in_memory_fallback():
                logger.error("v3 SQL evidence repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                raise
            logger.warning("v3 SQL evidence repo init failed, falling back to in-memory: %s", e)
            from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
            _evidence_repo = MemoryEvidenceRepository()
    else:
        from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
        _evidence_repo = MemoryEvidenceRepository()
    return _evidence_repo


def get_review_action_repo() -> ReviewActionRepository:
    global _review_action_repo
    if _review_action_repo is not None:
        return _review_action_repo
    if _v3_db_enabled():
        try:
            client = _get_v3_sql_client()
            from src.infrastructure.repositories.sql_review_action_repository import SqlReviewActionRepository
            _review_action_repo = SqlReviewActionRepository(client)
            logger.info("v3 ReviewActionRepository: using SQL backend")
        except Exception as e:
            if not _v3_allow_in_memory_fallback():
                logger.error("v3 SQL review_action repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                raise
            logger.warning("v3 SQL review_action repo init failed, falling back to in-memory: %s", e)
            from src.infrastructure.repositories.memory_review_action_repository import MemoryReviewActionRepository
            _review_action_repo = MemoryReviewActionRepository()
    else:
        from src.infrastructure.repositories.memory_review_action_repository import MemoryReviewActionRepository
        _review_action_repo = MemoryReviewActionRepository()
    return _review_action_repo


def get_metrics_calculator() -> MetricsCalculator:
    global _metrics_calculator
    if _metrics_calculator is not None:
        return _metrics_calculator
    from src.infrastructure.services.inventory_metrics_service import InventoryMetricsService
    _metrics_calculator = InventoryMetricsService(
        aisle_repo=get_aisle_repo(),
        position_repo=get_position_repo(),
    )
    return _metrics_calculator


def get_clock() -> Clock:
    from src.infrastructure.adapters.clock import UtcClock
    return UtcClock()


# --- v3.2.3 label consolidation (in-memory only for now) ---


def get_raw_label_repo() -> RawLabelRepository:
    global _raw_label_repo
    if _raw_label_repo is not None:
        return _raw_label_repo
    from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository
    _raw_label_repo = MemoryRawLabelRepository()
    return _raw_label_repo


def get_normalized_label_repo() -> NormalizedLabelRepository:
    global _normalized_label_repo
    if _normalized_label_repo is not None:
        return _normalized_label_repo
    from src.infrastructure.repositories.memory_normalized_label_repository import MemoryNormalizedLabelRepository
    _normalized_label_repo = MemoryNormalizedLabelRepository()
    return _normalized_label_repo


def get_final_count_repo() -> FinalCountRepository:
    global _final_count_repo
    if _final_count_repo is not None:
        return _final_count_repo
    if _v3_db_enabled():
        try:
            client = _get_v3_sql_client()
            from src.infrastructure.repositories.sql_final_count_repository import SqlFinalCountRepository
            _final_count_repo = SqlFinalCountRepository(client)
            logger.info("v3 FinalCountRepository: using SQL backend")
        except Exception as e:
            if not _v3_allow_in_memory_fallback():
                logger.error("v3 SQL final_count repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                raise
            logger.warning("v3 SQL final_count repo init failed, falling back to in-memory: %s", e)
            from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
            _final_count_repo = MemoryFinalCountRepository()
    else:
        from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
        _final_count_repo = MemoryFinalCountRepository()
    return _final_count_repo


def get_recompute_consolidated_counts_use_case():
    from src.application.use_cases.recompute_consolidated_counts import RecomputeConsolidatedCountsUseCase
    from src.application.services.label_normalization import LabelNormalizationService
    from src.application.services.final_count_builder import FinalCountBuilder
    from src.domain.labels.merge import MergeRuleEngine
    return RecomputeConsolidatedCountsUseCase(
        raw_label_repo=get_raw_label_repo(),
        normalized_label_repo=get_normalized_label_repo(),
        final_count_repo=get_final_count_repo(),
        product_record_repo=get_product_record_repo(),
        position_repo=get_position_repo(),
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )
