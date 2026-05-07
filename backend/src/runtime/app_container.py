"""
Explicit composition root for v3 runtime wiring (Phase 1).

Authoritative construction of shared repos, SQL client, artifact storage, and small services
used by both the FastAPI layer and background workers. API `dependencies.py` and
`runtime/v3_deps.py` delegate here — do not duplicate lazy singleton graphs elsewhere.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from src.application.ports.analytics_repository import AnalyticsRepository
from src.application.ports.capture_repositories import (
    CaptureSessionConfirmIdempotencyRepository,
    CaptureSessionGroupRepository,
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    ClientSupplierRepository,
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
from src.application.ports.services import ArtifactStorage, MetricsCalculator, WorkerLaunchService
from src.application.ports.stored_artifact_reader import StoredArtifactReader
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsUseCase,
)
from src.config import AppSettings
from src.database.sqlserver import SqlServerClient

logger = logging.getLogger(__name__)

_RepoT = TypeVar("_RepoT")

_container: AppContainer | None = None


def get_app_container() -> AppContainer:
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

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._v3_sql_client: SqlServerClient | None = None
        self._inventory_repo: InventoryRepository | None = None
        self._client_repo: ClientRepository | None = None
        self._client_supplier_repo: ClientSupplierRepository | None = None
        self._aisle_repo: AisleRepository | None = None
        self._job_repo: JobRepository | None = None
        self._asset_repo: SourceAssetRepository | None = None
        self._visual_reference_repo: InventoryVisualReferenceRepository | None = None
        self._position_repo: PositionRepository | None = None
        self._product_record_repo: ProductRecordRepository | None = None
        self._evidence_repo: EvidenceRepository | None = None
        self._review_action_repo: ReviewActionRepository | None = None
        self._metrics_calculator: MetricsCalculator | None = None
        self._raw_label_repo: RawLabelRepository | None = None
        self._normalized_label_repo: NormalizedLabelRepository | None = None
        self._final_count_repo: FinalCountRepository | None = None
        self._artifact_storage: ArtifactStorage | None = None
        self._worker_launch_service: WorkerLaunchService | None = None
        self._analytics_repo: AnalyticsRepository | None = None
        self._capture_session_repo: CaptureSessionRepository | None = None
        self._capture_session_item_repo: CaptureSessionItemRepository | None = None
        self._capture_session_confirm_repo: CaptureSessionConfirmIdempotencyRepository | None = None
        self._capture_session_group_repo: CaptureSessionGroupRepository | None = None
        self._stored_artifact_reader: StoredArtifactReader | None = None

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @staticmethod
    def _v3_allow_in_memory_fallback() -> bool:
        raw = (os.getenv("V3_ALLOW_IN_MEMORY_FALLBACK") or "true").strip().lower()
        return raw in ("true", "1", "yes")

    def _v3_db_enabled(self) -> bool:
        return bool(
            getattr(self._settings, "sqlserver_enabled", False)
            and self._settings.sqlserver_effective_connection_string
        )

    def _get_v3_sql_client(self) -> SqlServerClient:
        if self._v3_sql_client is not None:
            return self._v3_sql_client
        client = SqlServerClient(self._settings.require_sqlserver_connection_string())
        with client.cursor() as cur:
            cur.execute("SELECT 1")
        self._v3_sql_client = client
        return self._v3_sql_client

    def _build_sql_repository_or_memory(
        self,
        *,
        backend_info_name: str,
        sql_error_subject: str,
        build_sql: Callable[[SqlServerClient], _RepoT],
        build_memory: Callable[[], _RepoT],
    ) -> _RepoT:
        """Shared v3 pattern: SQL when enabled and connectable, else memory (with env-controlled fallback)."""
        if not self._v3_db_enabled():
            return build_memory()
        try:
            client = self._get_v3_sql_client()
            repo = build_sql(client)
            logger.info("v3 %s: using SQL backend", backend_info_name)
            return repo
        except Exception as e:
            if not self._v3_allow_in_memory_fallback():
                logger.error(
                    "v3 SQL %s init failed and V3_ALLOW_IN_MEMORY_FALLBACK is false: %s",
                    sql_error_subject,
                    e,
                )
                raise
            logger.warning(
                "v3 SQL %s init failed, falling back to in-memory: %s",
                sql_error_subject,
                e,
            )
            return build_memory()

    def get_inventory_repo(self) -> InventoryRepository:
        if self._inventory_repo is not None:
            return self._inventory_repo

        def _sql(client: SqlServerClient) -> InventoryRepository:
            from src.infrastructure.repositories.sql_inventory_repository import (
                SqlInventoryRepository,
            )

            return SqlInventoryRepository(client)

        def _memory() -> InventoryRepository:
            from src.infrastructure.repositories.memory_inventory_repository import (
                MemoryInventoryRepository,
            )

            return MemoryInventoryRepository()

        self._inventory_repo = self._build_sql_repository_or_memory(
            backend_info_name="InventoryRepository",
            sql_error_subject="repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._inventory_repo

    def get_client_repo(self) -> ClientRepository:
        if self._client_repo is not None:
            return self._client_repo

        def _sql(client: SqlServerClient) -> ClientRepository:
            from src.infrastructure.repositories.sql_client_repository import SqlClientRepository

            return SqlClientRepository(client)

        def _memory() -> ClientRepository:
            from src.infrastructure.repositories.memory_client_repository import (
                MemoryClientRepository,
            )

            return MemoryClientRepository()

        self._client_repo = self._build_sql_repository_or_memory(
            backend_info_name="ClientRepository",
            sql_error_subject="client repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._client_repo

    def get_client_supplier_repo(self) -> ClientSupplierRepository:
        if self._client_supplier_repo is not None:
            return self._client_supplier_repo

        def _sql(client: SqlServerClient) -> ClientSupplierRepository:
            from src.infrastructure.repositories.sql_client_supplier_repository import (
                SqlClientSupplierRepository,
            )

            return SqlClientSupplierRepository(client)

        def _memory() -> ClientSupplierRepository:
            from src.infrastructure.repositories.memory_client_supplier_repository import (
                MemoryClientSupplierRepository,
            )

            return MemoryClientSupplierRepository()

        self._client_supplier_repo = self._build_sql_repository_or_memory(
            backend_info_name="ClientSupplierRepository",
            sql_error_subject="client_supplier repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._client_supplier_repo

    def get_aisle_repo(self) -> AisleRepository:
        if self._aisle_repo is not None:
            return self._aisle_repo

        def _sql(client: SqlServerClient) -> AisleRepository:
            from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository

            return SqlAisleRepository(client)

        def _memory() -> AisleRepository:
            from src.infrastructure.repositories.memory_aisle_repository import (
                MemoryAisleRepository,
            )

            return MemoryAisleRepository()

        self._aisle_repo = self._build_sql_repository_or_memory(
            backend_info_name="AisleRepository",
            sql_error_subject="aisle repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._aisle_repo

    def get_job_repo(self) -> JobRepository:
        if self._job_repo is not None:
            return self._job_repo

        def _sql(client: SqlServerClient) -> JobRepository:
            from src.infrastructure.repositories.sql_job_repository import SqlJobRepository

            return SqlJobRepository(client)

        def _memory() -> JobRepository:
            from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository

            return MemoryJobRepository()

        self._job_repo = self._build_sql_repository_or_memory(
            backend_info_name="JobRepository",
            sql_error_subject="job repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._job_repo

    def get_source_asset_repo(self) -> SourceAssetRepository:
        if self._asset_repo is not None:
            return self._asset_repo

        def _sql(client: SqlServerClient) -> SourceAssetRepository:
            from src.infrastructure.repositories.sql_source_asset_repository import (
                SqlSourceAssetRepository,
            )

            return SqlSourceAssetRepository(client)

        def _memory() -> SourceAssetRepository:
            from src.infrastructure.repositories.memory_source_asset_repository import (
                MemorySourceAssetRepository,
            )

            return MemorySourceAssetRepository()

        self._asset_repo = self._build_sql_repository_or_memory(
            backend_info_name="SourceAssetRepository",
            sql_error_subject="source_asset repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._asset_repo

    def get_inventory_visual_reference_repo(self) -> InventoryVisualReferenceRepository:
        if self._visual_reference_repo is not None:
            return self._visual_reference_repo

        def _sql(client: SqlServerClient) -> InventoryVisualReferenceRepository:
            from src.infrastructure.repositories.sql_inventory_visual_reference_repository import (
                SqlInventoryVisualReferenceRepository,
            )

            return SqlInventoryVisualReferenceRepository(client)

        def _memory() -> InventoryVisualReferenceRepository:
            from src.infrastructure.repositories.memory_inventory_visual_reference_repository import (
                MemoryInventoryVisualReferenceRepository,
            )

            return MemoryInventoryVisualReferenceRepository()

        self._visual_reference_repo = self._build_sql_repository_or_memory(
            backend_info_name="InventoryVisualReferenceRepository",
            sql_error_subject="inventory_visual_reference repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._visual_reference_repo

    def get_position_repo(self) -> PositionRepository:
        if self._position_repo is not None:
            return self._position_repo

        def _sql(client: SqlServerClient) -> PositionRepository:
            from src.infrastructure.repositories.sql_position_repository import (
                SqlPositionRepository,
            )

            return SqlPositionRepository(client)

        def _memory() -> PositionRepository:
            from src.infrastructure.repositories.memory_position_repository import (
                MemoryPositionRepository,
            )

            return MemoryPositionRepository()

        self._position_repo = self._build_sql_repository_or_memory(
            backend_info_name="PositionRepository",
            sql_error_subject="position repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._position_repo

    def get_product_record_repo(self) -> ProductRecordRepository:
        if self._product_record_repo is not None:
            return self._product_record_repo

        def _sql(client: SqlServerClient) -> ProductRecordRepository:
            from src.infrastructure.repositories.sql_product_record_repository import (
                SqlProductRecordRepository,
            )

            return SqlProductRecordRepository(client)

        def _memory() -> ProductRecordRepository:
            from src.infrastructure.repositories.memory_product_record_repository import (
                MemoryProductRecordRepository,
            )

            return MemoryProductRecordRepository()

        self._product_record_repo = self._build_sql_repository_or_memory(
            backend_info_name="ProductRecordRepository",
            sql_error_subject="product_record repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._product_record_repo

    def get_evidence_repo(self) -> EvidenceRepository:
        if self._evidence_repo is not None:
            return self._evidence_repo

        def _sql(client: SqlServerClient) -> EvidenceRepository:
            from src.infrastructure.repositories.sql_evidence_repository import (
                SqlEvidenceRepository,
            )

            return SqlEvidenceRepository(client)

        def _memory() -> EvidenceRepository:
            from src.infrastructure.repositories.memory_evidence_repository import (
                MemoryEvidenceRepository,
            )

            return MemoryEvidenceRepository()

        self._evidence_repo = self._build_sql_repository_or_memory(
            backend_info_name="EvidenceRepository",
            sql_error_subject="evidence repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._evidence_repo

    def get_review_action_repo(self) -> ReviewActionRepository:
        if self._review_action_repo is not None:
            return self._review_action_repo

        def _sql(client: SqlServerClient) -> ReviewActionRepository:
            from src.infrastructure.repositories.sql_review_action_repository import (
                SqlReviewActionRepository,
            )

            return SqlReviewActionRepository(client)

        def _memory() -> ReviewActionRepository:
            from src.infrastructure.repositories.memory_review_action_repository import (
                MemoryReviewActionRepository,
            )

            return MemoryReviewActionRepository()

        self._review_action_repo = self._build_sql_repository_or_memory(
            backend_info_name="ReviewActionRepository",
            sql_error_subject="review_action repo",
            build_sql=_sql,
            build_memory=_memory,
        )
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

    def get_artifact_storage(self) -> ArtifactStorage:
        """Configured artifact storage (local or S3) — canonical accessor for API + worker."""
        if self._artifact_storage is not None:
            return self._artifact_storage
        settings = self._settings
        provider = (settings.artifact_storage_provider or "local").strip().lower()
        if provider == "s3":
            from src.infrastructure.storage.s3_artifact_storage_adapter import (
                S3ArtifactStorageAdapter,
            )

            if not settings.artifact_s3_bucket:
                raise RuntimeError(
                    "ARTIFACT_S3_BUCKET is required when ARTIFACT_STORAGE_PROVIDER=s3"
                )
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

    def get_stored_artifact_reader(self) -> StoredArtifactReader:
        """Hybrid reads for stored job JSON / reports (port adapter; shared by API + worker)."""
        if self._stored_artifact_reader is not None:
            return self._stored_artifact_reader
        from src.infrastructure.artifacts.stored_artifact_reader import DefaultStoredArtifactReader

        self._stored_artifact_reader = DefaultStoredArtifactReader(
            self.get_job_repo(),
            self.get_artifact_storage(),
        )
        return self._stored_artifact_reader

    def get_worker_launch_service(self) -> WorkerLaunchService:
        if self._worker_launch_service is not None:
            return self._worker_launch_service
        from src.infrastructure.services.on_demand_worker_launch_service import (
            OnDemandWorkerLaunchService,
        )

        self._worker_launch_service = OnDemandWorkerLaunchService()
        return self._worker_launch_service

    def get_raw_label_repo(self) -> RawLabelRepository:
        if self._raw_label_repo is not None:
            return self._raw_label_repo

        def _sql(client: SqlServerClient) -> RawLabelRepository:
            from src.infrastructure.repositories.sql_raw_label_repository import (
                SqlRawLabelRepository,
            )

            return SqlRawLabelRepository(client)

        def _memory() -> RawLabelRepository:
            from src.infrastructure.repositories.memory_raw_label_repository import (
                MemoryRawLabelRepository,
            )

            return MemoryRawLabelRepository()

        self._raw_label_repo = self._build_sql_repository_or_memory(
            backend_info_name="RawLabelRepository",
            sql_error_subject="raw_label repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._raw_label_repo

    def get_normalized_label_repo(self) -> NormalizedLabelRepository:
        if self._normalized_label_repo is not None:
            return self._normalized_label_repo

        def _sql(client: SqlServerClient) -> NormalizedLabelRepository:
            from src.infrastructure.repositories.sql_normalized_label_repository import (
                SqlNormalizedLabelRepository,
            )

            return SqlNormalizedLabelRepository(client)

        def _memory() -> NormalizedLabelRepository:
            from src.infrastructure.repositories.memory_normalized_label_repository import (
                MemoryNormalizedLabelRepository,
            )

            return MemoryNormalizedLabelRepository()

        self._normalized_label_repo = self._build_sql_repository_or_memory(
            backend_info_name="NormalizedLabelRepository",
            sql_error_subject="normalized_label repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._normalized_label_repo

    def get_final_count_repo(self) -> FinalCountRepository:
        if self._final_count_repo is not None:
            return self._final_count_repo

        def _sql(client: SqlServerClient) -> FinalCountRepository:
            from src.infrastructure.repositories.sql_final_count_repository import (
                SqlFinalCountRepository,
            )

            return SqlFinalCountRepository(client)

        def _memory() -> FinalCountRepository:
            from src.infrastructure.repositories.memory_final_count_repository import (
                MemoryFinalCountRepository,
            )

            return MemoryFinalCountRepository()

        self._final_count_repo = self._build_sql_repository_or_memory(
            backend_info_name="FinalCountRepository",
            sql_error_subject="final_count repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._final_count_repo

    def get_analytics_repo(self) -> AnalyticsRepository:
        if self._analytics_repo is not None:
            return self._analytics_repo

        from src.infrastructure.repositories.memory_analytics_repository import (
            MemoryAnalyticsRepository,
        )
        from src.infrastructure.repositories.sql_analytics_repository import SqlAnalyticsRepository

        def _sql(client: SqlServerClient) -> AnalyticsRepository:
            return SqlAnalyticsRepository(client)

        def _memory() -> AnalyticsRepository:
            return MemoryAnalyticsRepository(
                self.get_inventory_repo(),
                self.get_aisle_repo(),
                self.get_position_repo(),
                self.get_product_record_repo(),
                self.get_review_action_repo(),
                self.get_job_repo(),
            )

        self._analytics_repo = self._build_sql_repository_or_memory(
            backend_info_name="AnalyticsRepository",
            sql_error_subject="analytics repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._analytics_repo

    def get_capture_session_repo(self) -> CaptureSessionRepository:
        if self._capture_session_repo is not None:
            return self._capture_session_repo

        from src.infrastructure.repositories.memory_capture_session_repository import (
            MemoryCaptureSessionRepository,
        )
        from src.infrastructure.repositories.sql_capture_session_repository import (
            SqlCaptureSessionRepository,
        )

        def _sql(client: SqlServerClient) -> CaptureSessionRepository:
            return SqlCaptureSessionRepository(client)

        def _memory() -> CaptureSessionRepository:
            return MemoryCaptureSessionRepository()

        self._capture_session_repo = self._build_sql_repository_or_memory(
            backend_info_name="CaptureSessionRepository",
            sql_error_subject="capture_session repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._capture_session_repo

    def get_capture_session_item_repo(self) -> CaptureSessionItemRepository:
        if self._capture_session_item_repo is not None:
            return self._capture_session_item_repo

        from src.infrastructure.repositories.memory_capture_session_item_repository import (
            MemoryCaptureSessionItemRepository,
        )
        from src.infrastructure.repositories.sql_capture_session_item_repository import (
            SqlCaptureSessionItemRepository,
        )

        def _sql(client: SqlServerClient) -> CaptureSessionItemRepository:
            return SqlCaptureSessionItemRepository(client)

        def _memory() -> CaptureSessionItemRepository:
            return MemoryCaptureSessionItemRepository()

        self._capture_session_item_repo = self._build_sql_repository_or_memory(
            backend_info_name="CaptureSessionItemRepository",
            sql_error_subject="capture_session_item repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._capture_session_item_repo

    def get_capture_session_group_repo(self) -> CaptureSessionGroupRepository:
        if self._capture_session_group_repo is not None:
            return self._capture_session_group_repo

        from src.infrastructure.repositories.memory_capture_session_group_repository import (
            MemoryCaptureSessionGroupRepository,
        )
        from src.infrastructure.repositories.sql_capture_session_group_repository import (
            SqlCaptureSessionGroupRepository,
        )

        def _sql(client: SqlServerClient) -> CaptureSessionGroupRepository:
            return SqlCaptureSessionGroupRepository(client)

        def _memory() -> CaptureSessionGroupRepository:
            return MemoryCaptureSessionGroupRepository(self.get_capture_session_item_repo())

        self._capture_session_group_repo = self._build_sql_repository_or_memory(
            backend_info_name="CaptureSessionGroupRepository",
            sql_error_subject="capture_session_group repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._capture_session_group_repo

    def get_capture_session_confirm_repo(self) -> CaptureSessionConfirmIdempotencyRepository:
        if self._capture_session_confirm_repo is not None:
            return self._capture_session_confirm_repo

        from src.infrastructure.repositories.memory_capture_session_confirm_idempotency_repository import (
            MemoryCaptureSessionConfirmIdempotencyRepository,
        )
        from src.infrastructure.repositories.sql_capture_session_confirm_idempotency_repository import (
            SqlCaptureSessionConfirmIdempotencyRepository,
        )

        def _sql(client: SqlServerClient) -> CaptureSessionConfirmIdempotencyRepository:
            return SqlCaptureSessionConfirmIdempotencyRepository(client)

        def _memory() -> CaptureSessionConfirmIdempotencyRepository:
            return MemoryCaptureSessionConfirmIdempotencyRepository()

        self._capture_session_confirm_repo = self._build_sql_repository_or_memory(
            backend_info_name="CaptureSessionConfirmIdempotencyRepository",
            sql_error_subject="capture_session_confirm repo",
            build_sql=_sql,
            build_memory=_memory,
        )
        return self._capture_session_confirm_repo

    def get_recompute_consolidated_counts_use_case(self) -> RecomputeConsolidatedCountsUseCase:
        from src.application.services.final_count_builder import FinalCountBuilder
        from src.application.services.label_normalization import LabelNormalizationService
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
