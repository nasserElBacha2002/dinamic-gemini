"""
Explicit composition root for v3 runtime wiring (Phase 1).

Authoritative construction of shared repos, SQL client, artifact storage, and small services
used by both the FastAPI layer and background workers. API `dependencies.py` and
`runtime/v3_deps.py` delegate here — do not duplicate lazy singleton graphs elsewhere.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    FinalCountRepository,
    InventoryRepository,
    InventoryVisualReferenceRepository,
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

_container: Optional["AppContainer"] = None


def get_app_container() -> "AppContainer":
    """Return the process-wide application container (lazy-initialized)."""
    global _container
    if _container is None:
        from src.config import load_settings

        _container = AppContainer(load_settings())
    return _container


def reset_app_container_for_tests() -> None:
    """Drop the cached container (unit tests / isolated wiring checks)."""
    global _container
    _container = None


class AppContainer:
    """Builds and caches cross-cutting infrastructure dependencies."""

    def __init__(self, settings: "AppSettings") -> None:
        self._settings = settings
        self._v3_sql_client: Any = None
        self._inventory_repo: Optional[InventoryRepository] = None
        self._aisle_repo: Optional[AisleRepository] = None
        self._job_repo: Optional[JobRepository] = None
        self._asset_repo: Optional[SourceAssetRepository] = None
        self._visual_reference_repo: Optional[InventoryVisualReferenceRepository] = None
        self._position_repo: Optional[PositionRepository] = None
        self._product_record_repo: Optional[ProductRecordRepository] = None
        self._evidence_repo: Optional[EvidenceRepository] = None
        self._review_action_repo: Optional[ReviewActionRepository] = None
        self._metrics_calculator: Optional[MetricsCalculator] = None
        self._raw_label_repo: Optional[RawLabelRepository] = None
        self._normalized_label_repo: Optional[NormalizedLabelRepository] = None
        self._final_count_repo: Optional[FinalCountRepository] = None
        self._artifact_storage: Any = None
        self._worker_launch_service: Any = None
        self._analytics_repo: Any = None

    @property
    def settings(self) -> "AppSettings":
        return self._settings

    @staticmethod
    def _v3_allow_in_memory_fallback() -> bool:
        raw = (os.getenv("V3_ALLOW_IN_MEMORY_FALLBACK") or "true").strip().lower()
        return raw in ("true", "1", "yes")

    def _v3_db_enabled(self) -> bool:
        return bool(
            getattr(self._settings, "sqlserver_enabled", False) and self._settings.sqlserver_effective_connection_string
        )

    def _get_v3_sql_client(self) -> Any:
        if self._v3_sql_client is not None:
            return self._v3_sql_client
        from src.database.sqlserver import SqlServerClient

        client = SqlServerClient(self._settings.require_sqlserver_connection_string())
        with client.cursor() as cur:
            cur.execute("SELECT 1")
        self._v3_sql_client = client
        return self._v3_sql_client

    def get_inventory_repo(self) -> InventoryRepository:
        if self._inventory_repo is not None:
            return self._inventory_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository

                self._inventory_repo = SqlInventoryRepository(client)
                logger.info("v3 InventoryRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository

                self._inventory_repo = MemoryInventoryRepository()
        else:
            from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository

            self._inventory_repo = MemoryInventoryRepository()
        return self._inventory_repo

    def get_aisle_repo(self) -> AisleRepository:
        if self._aisle_repo is not None:
            return self._aisle_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository

                self._aisle_repo = SqlAisleRepository(client)
                logger.info("v3 AisleRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL aisle repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL aisle repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository

                self._aisle_repo = MemoryAisleRepository()
        else:
            from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository

            self._aisle_repo = MemoryAisleRepository()
        return self._aisle_repo

    def get_job_repo(self) -> JobRepository:
        if self._job_repo is not None:
            return self._job_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_job_repository import SqlJobRepository

                self._job_repo = SqlJobRepository(client)
                logger.info("v3 JobRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL job repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL job repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository

                self._job_repo = MemoryJobRepository()
        else:
            from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository

            self._job_repo = MemoryJobRepository()
        return self._job_repo

    def get_source_asset_repo(self) -> SourceAssetRepository:
        if self._asset_repo is not None:
            return self._asset_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_source_asset_repository import SqlSourceAssetRepository

                self._asset_repo = SqlSourceAssetRepository(client)
                logger.info("v3 SourceAssetRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL source_asset repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL source_asset repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_source_asset_repository import MemorySourceAssetRepository

                self._asset_repo = MemorySourceAssetRepository()
        else:
            from src.infrastructure.repositories.memory_source_asset_repository import MemorySourceAssetRepository

            self._asset_repo = MemorySourceAssetRepository()
        return self._asset_repo

    def get_inventory_visual_reference_repo(self) -> InventoryVisualReferenceRepository:
        if self._visual_reference_repo is not None:
            return self._visual_reference_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_inventory_visual_reference_repository import (
                    SqlInventoryVisualReferenceRepository,
                )

                self._visual_reference_repo = SqlInventoryVisualReferenceRepository(client)
                logger.info("v3 InventoryVisualReferenceRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error(
                        "v3 SQL inventory_visual_reference repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s",
                        e,
                    )
                    raise
                logger.warning(
                    "v3 SQL inventory_visual_reference repo init failed, falling back to in-memory: %s",
                    e,
                )
                from src.infrastructure.repositories.memory_inventory_visual_reference_repository import (
                    MemoryInventoryVisualReferenceRepository,
                )

                self._visual_reference_repo = MemoryInventoryVisualReferenceRepository()
        else:
            from src.infrastructure.repositories.memory_inventory_visual_reference_repository import (
                MemoryInventoryVisualReferenceRepository,
            )

            self._visual_reference_repo = MemoryInventoryVisualReferenceRepository()
        return self._visual_reference_repo

    def get_position_repo(self) -> PositionRepository:
        if self._position_repo is not None:
            return self._position_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository

                self._position_repo = SqlPositionRepository(client)
                logger.info("v3 PositionRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL position repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL position repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository

                self._position_repo = MemoryPositionRepository()
        else:
            from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository

            self._position_repo = MemoryPositionRepository()
        return self._position_repo

    def get_product_record_repo(self) -> ProductRecordRepository:
        if self._product_record_repo is not None:
            return self._product_record_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_product_record_repository import SqlProductRecordRepository

                self._product_record_repo = SqlProductRecordRepository(client)
                logger.info("v3 ProductRecordRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL product_record repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL product_record repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository

                self._product_record_repo = MemoryProductRecordRepository()
        else:
            from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository

            self._product_record_repo = MemoryProductRecordRepository()
        return self._product_record_repo

    def get_evidence_repo(self) -> EvidenceRepository:
        if self._evidence_repo is not None:
            return self._evidence_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository

                self._evidence_repo = SqlEvidenceRepository(client)
                logger.info("v3 EvidenceRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL evidence repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL evidence repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository

                self._evidence_repo = MemoryEvidenceRepository()
        else:
            from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository

            self._evidence_repo = MemoryEvidenceRepository()
        return self._evidence_repo

    def get_review_action_repo(self) -> ReviewActionRepository:
        if self._review_action_repo is not None:
            return self._review_action_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_review_action_repository import SqlReviewActionRepository

                self._review_action_repo = SqlReviewActionRepository(client)
                logger.info("v3 ReviewActionRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL review_action repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL review_action repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_review_action_repository import MemoryReviewActionRepository

                self._review_action_repo = MemoryReviewActionRepository()
        else:
            from src.infrastructure.repositories.memory_review_action_repository import MemoryReviewActionRepository

            self._review_action_repo = MemoryReviewActionRepository()
        return self._review_action_repo

    def get_metrics_calculator(self) -> MetricsCalculator:
        if self._metrics_calculator is not None:
            return self._metrics_calculator
        from src.infrastructure.services.inventory_metrics_service import InventoryMetricsService

        self._metrics_calculator = InventoryMetricsService(
            aisle_repo=self.get_aisle_repo(),
            position_repo=self.get_position_repo(),
        )
        return self._metrics_calculator

    def get_clock(self) -> Clock:
        from src.infrastructure.adapters.clock import UtcClock

        return UtcClock()

    def get_artifact_storage(self) -> Any:
        """Configured artifact storage (local or S3) — canonical accessor for API + worker."""
        if self._artifact_storage is not None:
            return self._artifact_storage
        settings = self._settings
        provider = (settings.artifact_storage_provider or "local").strip().lower()
        if provider == "s3":
            from src.infrastructure.storage.s3_artifact_storage_adapter import S3ArtifactStorageAdapter

            if not settings.artifact_s3_bucket:
                raise RuntimeError("ARTIFACT_S3_BUCKET is required when ARTIFACT_STORAGE_PROVIDER=s3")
            self._artifact_storage = S3ArtifactStorageAdapter(
                bucket=settings.artifact_s3_bucket,
                region=settings.artifact_s3_region or None,
                prefix=settings.artifact_s3_prefix,
                signed_url_ttl_sec=settings.artifact_s3_signed_url_ttl_sec,
            )
            logger.info(
                "Artifact storage configured: provider=s3 bucket=%s region=%s prefix=%s signed_url_ttl_sec=%s legacy_local_read=%s",
                settings.artifact_s3_bucket,
                settings.artifact_s3_region or "<default>",
                settings.artifact_s3_prefix,
                settings.artifact_s3_signed_url_ttl_sec,
                settings.artifact_storage_legacy_local_read_enabled,
            )
            return self._artifact_storage

        from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter

        base = Path(settings.output_dir) / "v3_uploads"
        base.mkdir(parents=True, exist_ok=True)
        self._artifact_storage = V3ArtifactStorageAdapter(base)
        logger.info(
            "Artifact storage configured: provider=local base_path=%s legacy_local_read=%s",
            str(base),
            settings.artifact_storage_legacy_local_read_enabled,
        )
        return self._artifact_storage

    def get_worker_launch_service(self) -> Any:
        if self._worker_launch_service is not None:
            return self._worker_launch_service
        from src.infrastructure.services.on_demand_worker_launch_service import OnDemandWorkerLaunchService

        self._worker_launch_service = OnDemandWorkerLaunchService()
        return self._worker_launch_service

    def get_raw_label_repo(self) -> RawLabelRepository:
        if self._raw_label_repo is not None:
            return self._raw_label_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_raw_label_repository import SqlRawLabelRepository

                self._raw_label_repo = SqlRawLabelRepository(client)
                logger.info("v3 RawLabelRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL raw_label repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL raw_label repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository

                self._raw_label_repo = MemoryRawLabelRepository()
        else:
            from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository

            self._raw_label_repo = MemoryRawLabelRepository()
        return self._raw_label_repo

    def get_normalized_label_repo(self) -> NormalizedLabelRepository:
        if self._normalized_label_repo is not None:
            return self._normalized_label_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_normalized_label_repository import SqlNormalizedLabelRepository

                self._normalized_label_repo = SqlNormalizedLabelRepository(client)
                logger.info("v3 NormalizedLabelRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL normalized_label repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL normalized_label repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_normalized_label_repository import MemoryNormalizedLabelRepository

                self._normalized_label_repo = MemoryNormalizedLabelRepository()
        else:
            from src.infrastructure.repositories.memory_normalized_label_repository import MemoryNormalizedLabelRepository

            self._normalized_label_repo = MemoryNormalizedLabelRepository()
        return self._normalized_label_repo

    def get_final_count_repo(self) -> FinalCountRepository:
        if self._final_count_repo is not None:
            return self._final_count_repo
        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                from src.infrastructure.repositories.sql_final_count_repository import SqlFinalCountRepository

                self._final_count_repo = SqlFinalCountRepository(client)
                logger.info("v3 FinalCountRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL final_count repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL final_count repo init failed, falling back to in-memory: %s", e)
                from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository

                self._final_count_repo = MemoryFinalCountRepository()
        else:
            from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository

            self._final_count_repo = MemoryFinalCountRepository()
        return self._final_count_repo

    def get_analytics_repo(self) -> Any:
        if self._analytics_repo is not None:
            return self._analytics_repo
        from src.infrastructure.repositories.memory_analytics_repository import MemoryAnalyticsRepository
        from src.infrastructure.repositories.sql_analytics_repository import SqlAnalyticsRepository

        if self._v3_db_enabled():
            try:
                client = self._get_v3_sql_client()
                self._analytics_repo = SqlAnalyticsRepository(client)
                logger.info("v3 AnalyticsRepository: using SQL backend")
            except Exception as e:
                if not self._v3_allow_in_memory_fallback():
                    logger.error("v3 SQL analytics repo init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s", e)
                    raise
                logger.warning("v3 SQL analytics repo init failed, falling back to in-memory: %s", e)
                self._analytics_repo = MemoryAnalyticsRepository(
                    self.get_inventory_repo(),
                    self.get_aisle_repo(),
                    self.get_position_repo(),
                    self.get_product_record_repo(),
                    self.get_review_action_repo(),
                    self.get_job_repo(),
                )
        else:
            self._analytics_repo = MemoryAnalyticsRepository(
                self.get_inventory_repo(),
                self.get_aisle_repo(),
                self.get_position_repo(),
                self.get_product_record_repo(),
                self.get_review_action_repo(),
                self.get_job_repo(),
            )
        return self._analytics_repo

    def get_recompute_consolidated_counts_use_case(self) -> Any:
        from src.application.services.final_count_builder import FinalCountBuilder
        from src.application.services.label_normalization import LabelNormalizationService
        from src.application.use_cases.recompute_consolidated_counts import RecomputeConsolidatedCountsUseCase
        from src.domain.labels.merge import MergeRuleEngine

        return RecomputeConsolidatedCountsUseCase(
            raw_label_repo=self.get_raw_label_repo(),
            normalized_label_repo=self.get_normalized_label_repo(),
            final_count_repo=self.get_final_count_repo(),
            product_record_repo=self.get_product_record_repo(),
            position_repo=self.get_position_repo(),
            normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
            final_count_builder=FinalCountBuilder(),
        )
