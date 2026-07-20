"""
Explicit composition root for v3 runtime wiring (Phase 1).

Authoritative construction of shared repos, SQL client, artifact storage, and small services
used by both the FastAPI layer and background workers. API `dependencies.py` and
`runtime/v3_deps.py` delegate here — do not duplicate lazy singleton graphs elsewhere.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import TypeVar

from src.application.ports.analytics_repository import AnalyticsRepository
from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.artifact_publication_outbox_store import ArtifactPublicationOutboxStore
from src.application.ports.capture_repositories import (
    CaptureSessionConfirmIdempotencyRepository,
    CaptureSessionGroupRepository,
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.code_scan_repository import CodeScanRepository
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.job_result_unit_of_work import JobResultUnitOfWorkFactory
from src.application.ports.job_scoped_recompute import JobScopedRecomputeFactory
from src.application.ports.operational_job_promotion import OperationalJobPromotionRepository
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    ClientSupplierRepository,
    EvidenceRepository,
    FinalCountRepository,
    InventoryRepository,
    JobRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    ResultEvidenceRepository,
    ReviewActionRepository,
    SourceAssetRepository,
    SupplierPromptConfigRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.services import ArtifactStorage, MetricsCalculator, WorkerLaunchService
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
    SupplierReferenceAnnotationRepository,
)
from src.application.services.artifact_publication_dispatcher import ArtifactPublicationDispatcher
from src.application.services.artifact_recovery_source_resolver import (
    ArtifactRecoverySourceResolver,
)
from src.application.services.default_job_scoped_recompute_factory import (
    DefaultJobScopedRecomputeFactory,
)
from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.application.services.finalization_recovery_eligibility import (
    FinalizationRecoveryEligibility,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_artifact_verifier import JobArtifactVerifier
from src.application.services.job_domain_result_verifier import JobDomainResultVerifier
from src.application.services.operational_result_promotion_service import (
    OperationalResultPromotionService,
)
from src.application.use_cases.finalization_recovery.resume_job_finalization import (
    FinalizationRecoveryCoordinator,
)
from src.application.use_cases.finalization_recovery.verify_and_republish import (
    FinalizationRecoveryDependencies,
)
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsUseCase,
)
from src.application.use_cases.suppliers.manage_supplier_extraction_profiles import (
    ActivateSupplierExtractionProfileVersionUseCase,
    CloneSupplierExtractionProfileUseCase,
    CreateSupplierExtractionProfileVersionUseCase,
    GetActiveSupplierExtractionProfileUseCase,
    GetSupplierExtractionProfileByVersionUseCase,
    ListSupplierExtractionProfilesUseCase,
    ListSupplierReferenceAnnotationsUseCase,
    ReplaceSupplierReferenceAnnotationsUseCase,
)
from src.application.use_cases.suppliers.manage_supplier_prompt_configs import (
    ActivateSupplierPromptConfigVersionUseCase,
    CreateSupplierPromptConfigVersionUseCase,
    GetActiveSupplierPromptConfigUseCase,
    GetSupplierPromptConfigUseCase,
    ListSupplierPromptConfigsUseCase,
)
from src.config import AppSettings
from src.database.sqlserver import SqlServerClient
from src.infrastructure.persistence.memory_artifact_manifest_store import (
    MemoryArtifactManifestStore,
)
from src.infrastructure.persistence.memory_artifact_publication_outbox_store import (
    MemoryArtifactPublicationOutboxStore,
)
from src.infrastructure.persistence.memory_finalization_recovery_store import (
    MemoryFinalizationRecoveryStore,
)
from src.infrastructure.persistence.memory_finalization_stage_store import (
    MemoryFinalizationStageStore,
)
from src.infrastructure.persistence.memory_job_result_unit_of_work import (
    MemoryJobResultUnitOfWorkFactory,
)
from src.infrastructure.persistence.memory_operational_job_promotion_repository import (
    MemoryOperationalJobPromotionRepository,
)
from src.infrastructure.persistence.sql_artifact_manifest_store import SqlArtifactManifestStore
from src.infrastructure.persistence.sql_artifact_publication_outbox_store import (
    SqlArtifactPublicationOutboxStore,
)
from src.infrastructure.persistence.sql_finalization_recovery_store import (
    SqlFinalizationRecoveryStore,
)
from src.infrastructure.persistence.sql_finalization_stage_store import SqlFinalizationStageStore
from src.infrastructure.persistence.sql_job_result_unit_of_work import (
    SqlJobResultUnitOfWorkFactory,
)
from src.infrastructure.persistence.sql_operational_job_promotion_repository import (
    SqlOperationalJobPromotionRepository,
)
from src.infrastructure.storage.artifact_store import ArtifactStore
from src.runtime.container.analytics_builders import build_analytics_repository
from src.runtime.container.capture_session_builders import (
    build_capture_session_confirm_repository,
    build_capture_session_group_repository,
    build_capture_session_item_repository,
    build_capture_session_repository,
)
from src.runtime.container.label_builders import (
    build_final_count_repository,
    build_normalized_label_repository,
    build_raw_label_repository,
)
from src.runtime.container.extraction_profile_builders import (
    build_activate_supplier_extraction_profile_version_use_case,
    build_clone_supplier_extraction_profile_use_case,
    build_create_supplier_extraction_profile_version_use_case,
    build_get_active_supplier_extraction_profile_use_case,
    build_get_supplier_extraction_profile_by_version_use_case,
    build_list_supplier_extraction_profiles_use_case,
    build_list_supplier_reference_annotations_use_case,
    build_replace_supplier_reference_annotations_use_case,
)
from src.runtime.container.prompt_config_builders import (
    build_activate_supplier_prompt_config_version_use_case,
    build_create_supplier_prompt_config_version_use_case,
    build_get_active_supplier_prompt_config_use_case,
    build_get_supplier_prompt_config_use_case,
    build_list_supplier_prompt_configs_use_case,
)
from src.runtime.container.repository_backend import (
    RepositoryBackendMode,
    RepositoryBackendResolution,
    resolve_repository_backend_mode,
)
from src.runtime.container.repository_builders import (
    build_aisle_repository,
    build_client_repository,
    build_client_supplier_repository,
    build_code_scan_repository,
    build_evidence_repository,
    build_inventory_repository,
    build_job_repository,
    build_position_repository,
    build_product_record_repository,
    build_result_evidence_repository,
    build_review_action_repository,
    build_source_asset_repository,
    build_supplier_extraction_profile_repository,
    build_supplier_prompt_config_repository,
    build_supplier_reference_annotation_repository,
    build_supplier_reference_image_repository,
)
from src.runtime.container.runtime_environment import is_production_like_runtime
from src.runtime.container.service_builders import (
    build_clock,
    build_metrics_calculator,
    build_worker_launch_service,
)
from src.runtime.container.storage_builders import (
    build_artifact_storage,
    build_stored_artifact_reader,
)
from src.runtime.container.use_case_builders import (
    build_recompute_consolidated_counts_use_case,
)

logger = logging.getLogger(__name__)

_RepoT = TypeVar("_RepoT")

_container: AppContainer | None = None
_container_lock = threading.Lock()


def get_app_container() -> AppContainer:
    """Return the process-wide application container (lazy-initialized)."""
    global _container
    if _container is not None:
        return _container
    with _container_lock:
        if _container is None:
            from src.config import load_settings

            _container = AppContainer(load_settings())
        return _container


def reset_app_container_for_tests() -> None:
    """Drop the cached container (unit tests / isolated wiring checks)."""
    global _container
    with _container_lock:
        if _container is not None:
            _container.close()
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
        self._supplier_reference_image_repo: SupplierReferenceImageRepository | None = None
        self._supplier_prompt_config_repo: SupplierPromptConfigRepository | None = None
        self._supplier_extraction_profile_repo: SupplierExtractionProfileRepository | None = None
        self._supplier_reference_annotation_repo: SupplierReferenceAnnotationRepository | None = None
        self._position_repo: PositionRepository | None = None
        self._product_record_repo: ProductRecordRepository | None = None
        self._evidence_repo: EvidenceRepository | None = None
        self._result_evidence_repo: ResultEvidenceRepository | None = None
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
        self._code_scan_repo: CodeScanRepository | None = None
        self._stored_artifact_reader: StoredArtifactReader | None = None
        self._finalization_stage_store: FinalizationStageStore | None = None
        self._artifact_manifest_store: ArtifactManifestStore | None = None
        self._job_source_asset_repo = None
        self._manual_image_coverage_repo = None
        self._job_image_coverage_repo = None
        self._manual_image_result_uow_factory = None
        self._artifact_publication_outbox_store: ArtifactPublicationOutboxStore | None = None
        self._finalization_recovery_store = None
        self._repository_backend_resolution: RepositoryBackendResolution | None = None

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def _is_production_environment(self) -> bool:
        """True when common env vars (``APP_ENV``, ``ENVIRONMENT``, ``NODE_ENV``) indicate hosted prod."""
        return is_production_like_runtime()

    def _v3_allow_in_memory_fallback(self) -> bool:
        """Whether SQL probe failure may resolve to ``MEMORY_FALLBACK`` (C2 container-level policy).

        If ``V3_ALLOW_IN_MEMORY_FALLBACK`` is set, only ``true`` / ``1`` / ``yes`` enable fallback.
        If unset: non-production-like runtimes default to allowing fallback (local/dev); production-like
        runtimes default to disallowing it (fail-fast unless SQL is reachable).
        """
        raw = os.getenv("V3_ALLOW_IN_MEMORY_FALLBACK")
        if raw is not None:
            return raw.strip().lower() in ("true", "1", "yes")
        return not self._is_production_environment()

    def close(self) -> None:
        """Best-effort release of cached resources; safe and idempotent to call multiple times.

        ``SqlServerClient`` does not hold a long-lived ODBC connection (connections are per
        ``cursor()`` context); clearing the reference is sufficient. Optional ``close`` / ``dispose``
        / ``shutdown`` methods on other cached objects are invoked when present.
        """
        client = self._v3_sql_client
        if client is not None:
            closer = getattr(client, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception as exc:
                    logger.warning("AppContainer.close: SqlServerClient.close raised: %s", exc)

        for resource, label in (
            (self._artifact_storage, "artifact_storage"),
            (self._worker_launch_service, "worker_launch_service"),
        ):
            if resource is None:
                continue
            for method_name in ("close", "dispose", "shutdown"):
                fn = getattr(resource, method_name, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception as exc:
                        logger.warning(
                            "AppContainer.close: %s.%s raised: %s",
                            label,
                            method_name,
                            exc,
                        )
                    break

        self._v3_sql_client = None
        self._inventory_repo = None
        self._client_repo = None
        self._client_supplier_repo = None
        self._aisle_repo = None
        self._job_repo = None
        self._asset_repo = None
        self._supplier_reference_image_repo = None
        self._supplier_prompt_config_repo = None
        self._supplier_extraction_profile_repo = None
        self._supplier_reference_annotation_repo = None
        self._position_repo = None
        self._product_record_repo = None
        self._evidence_repo = None
        self._result_evidence_repo = None
        self._review_action_repo = None
        self._job_source_asset_repo = None
        self._manual_image_coverage_repo = None
        self._job_image_coverage_repo = None
        self._manual_image_result_uow_factory = None
        self._metrics_calculator = None
        self._raw_label_repo = None
        self._normalized_label_repo = None
        self._final_count_repo = None
        self._artifact_storage = None
        self._worker_launch_service = None
        self._analytics_repo = None
        self._capture_session_repo = None
        self._capture_session_item_repo = None
        self._capture_session_confirm_repo = None
        self._capture_session_group_repo = None
        self._code_scan_repo = None
        self._stored_artifact_reader = None
        self._repository_backend_resolution = None

    def _probe_sql_for_repository_backend(self) -> None:
        """Validate SQL connectivity and cache SqlServerClient.

        Returns ``None``. Caches ``self._v3_sql_client`` only after a successful ``SELECT 1``.
        Callers obtain the client via :meth:`_get_v3_sql_client`.
        """
        if self._v3_sql_client is not None:
            return
        client = SqlServerClient(self._settings.require_sqlserver_connection_string())
        with client.cursor() as cur:
            cur.execute("SELECT 1")
        self._v3_sql_client = client

    def _get_v3_sql_client(self) -> SqlServerClient:
        if self._v3_sql_client is not None:
            return self._v3_sql_client
        self._probe_sql_for_repository_backend()
        client = self._v3_sql_client
        if client is None:
            raise RuntimeError("v3 SQL client not available after probe")
        return client

    def _get_repository_backend_resolution(self) -> RepositoryBackendResolution:
        """Resolve and cache SQL vs memory backend once per container (Phase C1 foundation)."""
        if self._repository_backend_resolution is not None:
            return self._repository_backend_resolution
        policy_allow = self._v3_allow_in_memory_fallback()
        v3_fallback_env_set = os.getenv("V3_ALLOW_IN_MEMORY_FALLBACK") is not None
        logger.info(
            "v3 repository_backend policy: allow_in_memory_fallback=%s production_like_runtime=%s "
            "v3_allow_in_memory_fallback_env_explicit=%s",
            policy_allow,
            self._is_production_environment(),
            v3_fallback_env_set,
        )
        res = resolve_repository_backend_mode(
            settings=self._settings,
            probe_sql=self._probe_sql_for_repository_backend,
            allow_in_memory_fallback=self._v3_allow_in_memory_fallback,
        )
        self._repository_backend_resolution = res
        sqlserver_enabled_flag = bool(getattr(self._settings, "sqlserver_enabled", False))
        sql_target_enabled = res.sql_enabled
        log_msg = (
            "v3 repository_backend resolved: mode=%s sqlserver_enabled_flag=%s "
            "sql_target_enabled=%s fallback_allowed=%s reason=%s"
        )
        log_args = (
            res.mode.value,
            sqlserver_enabled_flag,
            sql_target_enabled,
            res.fallback_allowed,
            res.reason or "",
        )
        if res.mode == RepositoryBackendMode.MEMORY_FALLBACK:
            logger.warning(log_msg, *log_args)
        else:
            logger.info(log_msg, *log_args)
        return res

    def is_sql_repository_backend(self) -> bool:
        """True when this container's resolved backend is SQL (not memory-only/fallback).

        Callers that build optional collaborators (e.g. the Phase 2 image-processing bridge)
        use this to decide whether an in-memory repository fallback would be inconsistent
        with the rest of the app's persistence (``require_sql``).
        """
        return self._get_repository_backend_resolution().mode == RepositoryBackendMode.SQL

    def _build_sql_repository_or_memory(
        self,
        *,
        backend_info_name: str,
        sql_error_subject: str,
        build_sql: Callable[[SqlServerClient], _RepoT],
        build_memory: Callable[[], _RepoT],
    ) -> _RepoT:
        """Build a repository using the container's single resolved backend mode (Phase C2).

        Fallback to memory occurs only when the cached resolution is ``MEMORY_ONLY`` or
        ``MEMORY_FALLBACK`` (resolved once at container level). In ``SQL`` mode, ``build_sql`` failures
        propagate — no per-repository memory fallback.
        """
        _ = sql_error_subject  # retained for call-site parity / future diagnostics
        resolution = self._get_repository_backend_resolution()
        if resolution.mode in (
            RepositoryBackendMode.MEMORY_ONLY,
            RepositoryBackendMode.MEMORY_FALLBACK,
        ):
            return build_memory()
        if resolution.mode == RepositoryBackendMode.SQL:
            client = self._get_v3_sql_client()
            repo = build_sql(client)
            logger.info("v3 %s: using SQL backend", backend_info_name)
            return repo
        raise RuntimeError(f"Unsupported repository backend mode: {resolution.mode!r}")

    def get_inventory_repo(self) -> InventoryRepository:
        if self._inventory_repo is not None:
            return self._inventory_repo
        self._inventory_repo = build_inventory_repository(self._build_sql_repository_or_memory)
        return self._inventory_repo

    def get_client_repo(self) -> ClientRepository:
        if self._client_repo is not None:
            return self._client_repo
        self._client_repo = build_client_repository(self._build_sql_repository_or_memory)
        return self._client_repo

    def get_client_supplier_repo(self) -> ClientSupplierRepository:
        if self._client_supplier_repo is not None:
            return self._client_supplier_repo
        self._client_supplier_repo = build_client_supplier_repository(
            self._build_sql_repository_or_memory
        )
        return self._client_supplier_repo

    def get_aisle_repo(self) -> AisleRepository:
        if self._aisle_repo is not None:
            return self._aisle_repo
        self._aisle_repo = build_aisle_repository(self._build_sql_repository_or_memory)
        return self._aisle_repo

    def get_job_repo(self) -> JobRepository:
        if self._job_repo is not None:
            return self._job_repo
        self._job_repo = build_job_repository(self._build_sql_repository_or_memory)
        return self._job_repo

    def get_source_asset_repo(self) -> SourceAssetRepository:
        if self._asset_repo is not None:
            return self._asset_repo
        self._asset_repo = build_source_asset_repository(self._build_sql_repository_or_memory)
        return self._asset_repo

    def get_code_scan_repo(self) -> CodeScanRepository:
        if self._code_scan_repo is not None:
            return self._code_scan_repo
        self._code_scan_repo = build_code_scan_repository(self._build_sql_repository_or_memory)
        return self._code_scan_repo

    def get_supplier_reference_image_repo(self) -> SupplierReferenceImageRepository:
        if self._supplier_reference_image_repo is not None:
            return self._supplier_reference_image_repo
        self._supplier_reference_image_repo = build_supplier_reference_image_repository(
            self._build_sql_repository_or_memory
        )
        return self._supplier_reference_image_repo

    def get_supplier_prompt_config_repo(self) -> SupplierPromptConfigRepository:
        if self._supplier_prompt_config_repo is not None:
            return self._supplier_prompt_config_repo
        self._supplier_prompt_config_repo = build_supplier_prompt_config_repository(
            self._build_sql_repository_or_memory
        )
        return self._supplier_prompt_config_repo

    def get_supplier_extraction_profile_repo(self) -> SupplierExtractionProfileRepository:
        if self._supplier_extraction_profile_repo is not None:
            return self._supplier_extraction_profile_repo
        self._supplier_extraction_profile_repo = build_supplier_extraction_profile_repository(
            self._build_sql_repository_or_memory
        )
        return self._supplier_extraction_profile_repo

    def get_supplier_reference_annotation_repo(self) -> SupplierReferenceAnnotationRepository:
        if self._supplier_reference_annotation_repo is not None:
            return self._supplier_reference_annotation_repo
        self._supplier_reference_annotation_repo = build_supplier_reference_annotation_repository(
            self._build_sql_repository_or_memory
        )
        return self._supplier_reference_annotation_repo

    def get_position_repo(self) -> PositionRepository:
        if self._position_repo is not None:
            return self._position_repo
        self._position_repo = build_position_repository(self._build_sql_repository_or_memory)
        return self._position_repo

    def get_product_record_repo(self) -> ProductRecordRepository:
        if self._product_record_repo is not None:
            return self._product_record_repo
        self._product_record_repo = build_product_record_repository(
            self._build_sql_repository_or_memory
        )
        return self._product_record_repo

    def get_evidence_repo(self) -> EvidenceRepository:
        if self._evidence_repo is not None:
            return self._evidence_repo
        self._evidence_repo = build_evidence_repository(self._build_sql_repository_or_memory)
        return self._evidence_repo

    def get_result_evidence_repo(self) -> ResultEvidenceRepository:
        if self._result_evidence_repo is not None:
            return self._result_evidence_repo
        self._result_evidence_repo = build_result_evidence_repository(
            self._build_sql_repository_or_memory
        )
        return self._result_evidence_repo

    def get_review_action_repo(self) -> ReviewActionRepository:
        if self._review_action_repo is not None:
            return self._review_action_repo
        self._review_action_repo = build_review_action_repository(
            self._build_sql_repository_or_memory
        )
        return self._review_action_repo

    def get_metrics_calculator(self) -> MetricsCalculator:
        if self._metrics_calculator is not None:
            return self._metrics_calculator
        self._metrics_calculator = build_metrics_calculator(
            aisle_repo=self.get_aisle_repo(),
            position_repo=self.get_position_repo(),
        )
        return self._metrics_calculator

    def get_clock(self) -> Clock:
        return build_clock()

    def get_artifact_storage(self) -> ArtifactStorage:
        """Configured artifact storage (local or S3) — canonical accessor for API + worker."""
        if self._artifact_storage is not None:
            return self._artifact_storage
        self._artifact_storage = build_artifact_storage(self._settings)
        return self._artifact_storage

    def get_artifact_store(self) -> ArtifactStore:
        """Provider-aware artifact store for publication verification and recovery."""
        storage = self.get_artifact_storage()
        if not isinstance(storage, ArtifactStore):
            raise RuntimeError(
                f"Artifact storage {type(storage).__name__} does not implement ArtifactStore"
            )
        return storage

    def get_stored_artifact_reader(self) -> StoredArtifactReader:
        """Hybrid reads for stored job JSON / reports (port adapter; shared by API + worker)."""
        if self._stored_artifact_reader is not None:
            return self._stored_artifact_reader
        self._stored_artifact_reader = build_stored_artifact_reader(
            job_repo=self.get_job_repo(),
            artifact_storage=self.get_artifact_storage(),
        )
        return self._stored_artifact_reader

    def get_worker_launch_service(self) -> WorkerLaunchService:
        if self._worker_launch_service is not None:
            return self._worker_launch_service
        self._worker_launch_service = build_worker_launch_service()
        return self._worker_launch_service

    def get_raw_label_repo(self) -> RawLabelRepository:
        if self._raw_label_repo is not None:
            return self._raw_label_repo
        self._raw_label_repo = build_raw_label_repository(self._build_sql_repository_or_memory)
        return self._raw_label_repo

    def get_normalized_label_repo(self) -> NormalizedLabelRepository:
        if self._normalized_label_repo is not None:
            return self._normalized_label_repo
        self._normalized_label_repo = build_normalized_label_repository(
            self._build_sql_repository_or_memory
        )
        return self._normalized_label_repo

    def get_final_count_repo(self) -> FinalCountRepository:
        if self._final_count_repo is not None:
            return self._final_count_repo
        self._final_count_repo = build_final_count_repository(self._build_sql_repository_or_memory)
        return self._final_count_repo

    def get_analytics_repo(self) -> AnalyticsRepository:
        if self._analytics_repo is not None:
            return self._analytics_repo
        self._analytics_repo = build_analytics_repository(
            self._build_sql_repository_or_memory,
            get_inventory_repo=self.get_inventory_repo,
            get_aisle_repo=self.get_aisle_repo,
            get_position_repo=self.get_position_repo,
            get_product_record_repo=self.get_product_record_repo,
            get_review_action_repo=self.get_review_action_repo,
            get_job_repo=self.get_job_repo,
        )
        return self._analytics_repo

    def get_capture_session_repo(self) -> CaptureSessionRepository:
        if self._capture_session_repo is not None:
            return self._capture_session_repo
        self._capture_session_repo = build_capture_session_repository(
            self._build_sql_repository_or_memory
        )
        return self._capture_session_repo

    def get_capture_session_item_repo(self) -> CaptureSessionItemRepository:
        if self._capture_session_item_repo is not None:
            return self._capture_session_item_repo
        self._capture_session_item_repo = build_capture_session_item_repository(
            self._build_sql_repository_or_memory
        )
        return self._capture_session_item_repo

    def get_capture_session_group_repo(self) -> CaptureSessionGroupRepository:
        if self._capture_session_group_repo is not None:
            return self._capture_session_group_repo
        self._capture_session_group_repo = build_capture_session_group_repository(
            self._build_sql_repository_or_memory,
            get_capture_session_item_repo=self.get_capture_session_item_repo,
        )
        return self._capture_session_group_repo

    def get_capture_session_confirm_repo(self) -> CaptureSessionConfirmIdempotencyRepository:
        if self._capture_session_confirm_repo is not None:
            return self._capture_session_confirm_repo
        self._capture_session_confirm_repo = build_capture_session_confirm_repository(
            self._build_sql_repository_or_memory
        )
        return self._capture_session_confirm_repo

    def get_recompute_consolidated_counts_use_case(self) -> RecomputeConsolidatedCountsUseCase:
        return build_recompute_consolidated_counts_use_case(
            raw_label_repo=self.get_raw_label_repo(),
            normalized_label_repo=self.get_normalized_label_repo(),
            final_count_repo=self.get_final_count_repo(),
            product_record_repo=self.get_product_record_repo(),
            position_repo=self.get_position_repo(),
        )

    def get_finalization_stage_store(self) -> FinalizationStageStore:
        if self._finalization_stage_store is not None:
            return self._finalization_stage_store
        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._finalization_stage_store = SqlFinalizationStageStore(self._get_v3_sql_client())
        else:
            self._finalization_stage_store = MemoryFinalizationStageStore()
        return self._finalization_stage_store

    def get_artifact_manifest_store(self) -> ArtifactManifestStore:
        if self._artifact_manifest_store is not None:
            return self._artifact_manifest_store
        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._artifact_manifest_store = SqlArtifactManifestStore(self._get_v3_sql_client())
        else:
            self._artifact_manifest_store = MemoryArtifactManifestStore()
        return self._artifact_manifest_store

    def get_job_source_asset_repo(self):
        if self._job_source_asset_repo is not None:
            return self._job_source_asset_repo
        from src.infrastructure.persistence.memory_job_source_asset_repository import (
            MemoryJobSourceAssetRepository,
        )
        from src.infrastructure.persistence.sql_job_source_asset_repository import (
            SqlJobSourceAssetRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._job_source_asset_repo = SqlJobSourceAssetRepository(self._get_v3_sql_client())
        else:
            self._job_source_asset_repo = MemoryJobSourceAssetRepository()
        return self._job_source_asset_repo

    def get_job_asset_processing_state_repo(self):
        if getattr(self, "_job_asset_processing_state_repo", None) is not None:
            return self._job_asset_processing_state_repo
        from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
            MemoryJobAssetProcessingStateRepository,
        )
        from src.infrastructure.repositories.sql_job_asset_processing_state_repository import (
            SqlJobAssetProcessingStateRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._job_asset_processing_state_repo = SqlJobAssetProcessingStateRepository(
                self._get_v3_sql_client()
            )
        else:
            self._job_asset_processing_state_repo = MemoryJobAssetProcessingStateRepository()
        return self._job_asset_processing_state_repo

    def get_processing_attempt_repo(self):
        if getattr(self, "_processing_attempt_repo", None) is not None:
            return self._processing_attempt_repo
        from src.infrastructure.repositories.memory_processing_attempt_repository import (
            MemoryProcessingAttemptRepository,
        )
        from src.infrastructure.repositories.sql_processing_attempt_repository import (
            SqlProcessingAttemptRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._processing_attempt_repo = SqlProcessingAttemptRepository(
                self._get_v3_sql_client()
            )
        else:
            self._processing_attempt_repo = MemoryProcessingAttemptRepository()
        return self._processing_attempt_repo

    def get_external_image_analysis_request_repo(self):
        """Durable external fallback claims (Phase 5 corrections — SQL when available)."""
        if getattr(self, "_external_image_analysis_request_repo", None) is not None:
            return self._external_image_analysis_request_repo
        from src.infrastructure.repositories.memory_external_image_analysis_request_repository import (
            MemoryExternalImageAnalysisRequestRepository,
        )
        from src.infrastructure.repositories.sql_external_image_analysis_request_repository import (
            SqlExternalImageAnalysisRequestRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._external_image_analysis_request_repo = (
                SqlExternalImageAnalysisRequestRepository(self._get_v3_sql_client())
            )
        else:
            self._external_image_analysis_request_repo = (
                MemoryExternalImageAnalysisRequestRepository()
            )
        return self._external_image_analysis_request_repo

    def get_processing_event_repo(self):
        """Phase 7 structured processing events (memory or SQL)."""
        if getattr(self, "_processing_event_repo", None) is not None:
            return self._processing_event_repo
        from src.infrastructure.repositories.memory_processing_event_repository import (
            MemoryProcessingEventRepository,
        )
        from src.infrastructure.repositories.sql_processing_event_repository import (
            SqlProcessingEventRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._processing_event_repo = SqlProcessingEventRepository(
                self._get_v3_sql_client()
            )
        else:
            self._processing_event_repo = MemoryProcessingEventRepository()
        return self._processing_event_repo

    def get_asset_processing_command_repo(self):
        if getattr(self, "_asset_processing_command_repo", None) is not None:
            return self._asset_processing_command_repo
        from src.infrastructure.repositories.memory_asset_processing_command_repository import (
            MemoryAssetProcessingCommandRepository,
        )
        from src.infrastructure.repositories.sql_asset_processing_command_repository import (
            SqlAssetProcessingCommandRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._asset_processing_command_repo = SqlAssetProcessingCommandRepository(
                self._get_v3_sql_client()
            )
        else:
            self._asset_processing_command_repo = MemoryAssetProcessingCommandRepository()
        return self._asset_processing_command_repo

    def get_processing_action_idempotency_repo(self):
        if getattr(self, "_processing_action_idempotency_repo", None) is not None:
            return self._processing_action_idempotency_repo
        from src.infrastructure.repositories.memory_processing_action_idempotency_repository import (
            MemoryProcessingActionIdempotencyRepository,
        )
        from src.infrastructure.repositories.sql_processing_action_idempotency_repository import (
            SqlProcessingActionIdempotencyRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._processing_action_idempotency_repo = (
                SqlProcessingActionIdempotencyRepository(self._get_v3_sql_client())
            )
        else:
            self._processing_action_idempotency_repo = (
                MemoryProcessingActionIdempotencyRepository()
            )
        return self._processing_action_idempotency_repo

    def get_job_processing_lease_repo(self):
        if getattr(self, "_job_processing_lease_repo", None) is not None:
            return self._job_processing_lease_repo
        from src.infrastructure.repositories.memory_job_processing_lease_repository import (
            MemoryJobProcessingLeaseRepository,
        )
        from src.infrastructure.repositories.sql_job_processing_lease_repository import (
            SqlJobProcessingLeaseRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._job_processing_lease_repo = SqlJobProcessingLeaseRepository(
                self._get_v3_sql_client()
            )
        else:
            self._job_processing_lease_repo = MemoryJobProcessingLeaseRepository()
        return self._job_processing_lease_repo

    def get_batch_processing_attempt_repo(self):
        if getattr(self, "_batch_processing_attempt_repo", None) is not None:
            return self._batch_processing_attempt_repo
        from src.infrastructure.repositories.memory_batch_processing_attempt_repository import (
            MemoryBatchProcessingAttemptRepository,
        )
        from src.infrastructure.repositories.sql_batch_processing_attempt_repository import (
            SqlBatchProcessingAttemptRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._batch_processing_attempt_repo = SqlBatchProcessingAttemptRepository(
                self._get_v3_sql_client()
            )
        else:
            self._batch_processing_attempt_repo = MemoryBatchProcessingAttemptRepository()
        return self._batch_processing_attempt_repo

    def get_manual_image_coverage_repo(self):
        if self._manual_image_coverage_repo is not None:
            return self._manual_image_coverage_repo
        from src.infrastructure.persistence.memory_manual_image_coverage_repository import (
            MemoryManualImageCoverageRepository,
        )
        from src.infrastructure.persistence.sql_manual_image_coverage_repository import (
            SqlManualImageCoverageRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._manual_image_coverage_repo = SqlManualImageCoverageRepository(
                self._get_v3_sql_client()
            )
        else:
            self._manual_image_coverage_repo = MemoryManualImageCoverageRepository()
        return self._manual_image_coverage_repo

    def get_job_image_coverage_repo(self):
        if self._job_image_coverage_repo is not None:
            return self._job_image_coverage_repo
        from src.infrastructure.persistence.memory_job_image_coverage_repository import (
            MemoryJobImageCoverageRepository,
        )
        from src.infrastructure.persistence.sql_job_image_coverage_repository import (
            SqlJobImageCoverageRepository,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._job_image_coverage_repo = SqlJobImageCoverageRepository(
                self._get_v3_sql_client()
            )
        else:
            self._job_image_coverage_repo = MemoryJobImageCoverageRepository(
                job_source_asset_repo=self.get_job_source_asset_repo(),
                position_repo=self.get_position_repo(),
                result_evidence_repo=self.get_result_evidence_repo(),
            )
        return self._job_image_coverage_repo

    def get_manual_image_result_uow_factory(self):
        if self._manual_image_result_uow_factory is not None:
            return self._manual_image_result_uow_factory
        from src.application.ports.manual_image_result_unit_of_work import (
            ManualImageResultRepositories,
        )
        from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
        from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
        from src.infrastructure.persistence.memory_manual_image_result_unit_of_work import (
            build_memory_manual_image_result_uow_factory,
        )
        from src.infrastructure.persistence.sql_manual_image_result_unit_of_work import (
            build_sql_manual_image_result_uow_factory,
        )

        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            # SQL UoW builds its own transactional lifecycle on the same connection.
            self._manual_image_result_uow_factory = build_sql_manual_image_result_uow_factory(
                self._get_v3_sql_client(),
                self.get_clock(),
            )
        else:
            lifecycle = AisleReviewLifecycleSync(
                aisle_repo=self.get_aisle_repo(),
                position_repo=self.get_position_repo(),
                clock=self.get_clock(),
                status_reconciler=InventoryStatusReconciler(
                    inventory_repo=self.get_inventory_repo(),
                    aisle_repo=self.get_aisle_repo(),
                    clock=self.get_clock(),
                ),
            )
            repos = ManualImageResultRepositories(
                position_repo=self.get_position_repo(),
                product_record_repo=self.get_product_record_repo(),
                evidence_repo=self.get_evidence_repo(),
                manual_coverage_repo=self.get_manual_image_coverage_repo(),
                result_evidence_repo=self.get_result_evidence_repo(),
                review_repo=self.get_review_action_repo(),
                image_coverage_repo=self.get_job_image_coverage_repo(),
            )
            self._manual_image_result_uow_factory = build_memory_manual_image_result_uow_factory(
                repos,
                lifecycle,
            )
        return self._manual_image_result_uow_factory

    def get_artifact_publication_outbox_store(self) -> ArtifactPublicationOutboxStore:
        if self._artifact_publication_outbox_store is not None:
            return self._artifact_publication_outbox_store
        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._artifact_publication_outbox_store = SqlArtifactPublicationOutboxStore(
                self._get_v3_sql_client()
            )
        else:
            self._artifact_publication_outbox_store = MemoryArtifactPublicationOutboxStore()
        return self._artifact_publication_outbox_store

    def get_artifact_staging_store(self):
        from src.infrastructure.artifacts.filesystem_artifact_staging_store import (
            FileSystemArtifactStagingStore,
        )

        base = self._settings.artifact_staging_base_path
        return FileSystemArtifactStagingStore(base)

    def get_artifact_publication_dispatcher(self) -> ArtifactPublicationDispatcher:
        from src.application.services.artifact_finalization_continuation import (
            ArtifactFinalizationContinuationCoordinator,
        )
        from src.application.services.artifact_publication_dispatcher import (
            ArtifactPublicationDispatcher,
        )
        from src.application.services.artifact_publication_state_reconciler import (
            ArtifactPublicationStateReconciler,
        )
        from src.application.services.automatic_finalization_continuation_use_case import (
            AutomaticFinalizationContinuationUseCase,
        )
        from src.application.services.finalization_projection_service import (
            FinalizationProjectionService,
        )
        from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
        from src.infrastructure.pipeline.finalization_stage_recorder import (
            FinalizationStageRecorder,
        )
        from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService

        settings = self._settings
        backoff = settings.parse_backoff_seconds(settings.artifact_publication_backoff_seconds)
        job_repo = self.get_job_repo()
        aisle_repo = self.get_aisle_repo()
        inventory_repo = self.get_inventory_repo()
        clock = self.get_clock()
        stage_store = self.get_finalization_stage_store()
        manifest_store = self.get_artifact_manifest_store()
        outbox_store = self.get_artifact_publication_outbox_store()
        artifact_store = self.get_artifact_store()
        state = V3JobExecutionStateService(
            job_repo=job_repo,
            aisle_repo=aisle_repo,
            inventory_repo=inventory_repo,
            clock=clock,
            inventory_status_reconciler=InventoryStatusReconciler(
                inventory_repo=inventory_repo,
                aisle_repo=aisle_repo,
                clock=clock,
            ),
            operational_promotion_service=self.get_operational_result_promotion_service(),
        )
        projection = FinalizationProjectionService(
            job_repo=job_repo,
            stage_store=stage_store,
            clock=clock,
        )
        recorder = FinalizationStageRecorder(
            stage_store=stage_store,
            projection=projection,
            manifest_store=manifest_store,
            clock=clock,
        )
        continuation = ArtifactFinalizationContinuationCoordinator(
            job_repo=job_repo,
            manifest_store=manifest_store,
            stage_store=stage_store,
            state_service=state,
        )
        automatic = AutomaticFinalizationContinuationUseCase(
            job_repo=job_repo,
            aisle_repo=aisle_repo,
            inventory_repo=inventory_repo,
            manifest_store=manifest_store,
            stage_store=stage_store,
            state_service=state,
            clock=clock,
        )
        reconciler = ArtifactPublicationStateReconciler(
            outbox_store=outbox_store,
            manifest_store=manifest_store,
            artifact_store=artifact_store,
            clock=clock,
        )
        return ArtifactPublicationDispatcher(
            outbox_store=outbox_store,
            manifest_store=manifest_store,
            stage_store=stage_store,
            artifact_store=artifact_store,
            stage_recorder=recorder,
            continuation=continuation,
            automatic_continuation=automatic,
            staging_store=self.get_artifact_staging_store(),
            reconciler=reconciler,
            clock=clock,
            lease_seconds=settings.artifact_publication_lease_seconds,
            max_attempts=settings.artifact_publication_max_attempts,
            backoff_seconds=backoff,
            claimed_by_prefix="artifact-outbox-worker",
        )

    def get_finalization_assessment_service(self) -> FinalizationAssessmentService:
        return FinalizationAssessmentService(
            job_repo=self.get_job_repo(),
            aisle_repo=self.get_aisle_repo(),
            stage_store=self.get_finalization_stage_store(),
            manifest_store=self.get_artifact_manifest_store(),
            domain_verifier=JobDomainResultVerifier(
                aisle_repo=self.get_aisle_repo(),
                position_repo=self.get_position_repo(),
                product_repo=self.get_product_record_repo(),
                evidence_repo=self.get_evidence_repo(),
                raw_label_repo=self.get_raw_label_repo(),
                normalized_label_repo=self.get_normalized_label_repo(),
                final_count_repo=self.get_final_count_repo(),
                stage_store=self.get_finalization_stage_store(),
            ),
            artifact_verifier=JobArtifactVerifier(
                manifest_store=self.get_artifact_manifest_store(),
                artifact_store=self.get_artifact_store(),
            ),
        )

    def get_finalization_recovery_store(self):
        if self._finalization_recovery_store is not None:
            return self._finalization_recovery_store
        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            self._finalization_recovery_store = SqlFinalizationRecoveryStore(self._get_v3_sql_client())
        else:
            self._finalization_recovery_store = MemoryFinalizationRecoveryStore()
        return self._finalization_recovery_store

    def get_finalization_recovery_coordinator(self) -> FinalizationRecoveryCoordinator:
        eligibility = FinalizationRecoveryEligibility()
        domain_verifier = JobDomainResultVerifier(
            aisle_repo=self.get_aisle_repo(),
            position_repo=self.get_position_repo(),
            product_repo=self.get_product_record_repo(),
            evidence_repo=self.get_evidence_repo(),
            raw_label_repo=self.get_raw_label_repo(),
            normalized_label_repo=self.get_normalized_label_repo(),
            final_count_repo=self.get_final_count_repo(),
            stage_store=self.get_finalization_stage_store(),
        )
        artifact_verifier = JobArtifactVerifier(
            manifest_store=self.get_artifact_manifest_store(),
            artifact_store=self.get_artifact_store(),
        )
        deps = FinalizationRecoveryDependencies(
            job_repo=self.get_job_repo(),
            aisle_repo=self.get_aisle_repo(),
            inventory_repo=self.get_inventory_repo(),
            stage_store=self.get_finalization_stage_store(),
            manifest_store=self.get_artifact_manifest_store(),
            recovery_store=self.get_finalization_recovery_store(),
            assessment_service=self.get_finalization_assessment_service(),
            domain_verifier=domain_verifier,
            artifact_verifier=artifact_verifier,
            source_resolver=ArtifactRecoverySourceResolver(
                artifact_verifier=artifact_verifier,
                output_dir=self._settings.output_dir,
            ),
            promotion_service=self.get_operational_result_promotion_service(),
            inventory_reconciler=InventoryStatusReconciler(
                inventory_repo=self.get_inventory_repo(),
                aisle_repo=self.get_aisle_repo(),
                clock=self.get_clock(),
            ),
            artifact_store=self.get_artifact_store(),
            clock=self.get_clock(),
            eligibility=eligibility,
        )
        return FinalizationRecoveryCoordinator(deps)

    def get_job_result_uow_factory(self) -> JobResultUnitOfWorkFactory:
        resolution = self._get_repository_backend_resolution()
        if resolution.mode == RepositoryBackendMode.SQL:
            return SqlJobResultUnitOfWorkFactory(self._get_v3_sql_client())
        stage_store = self.get_finalization_stage_store()
        if not isinstance(stage_store, MemoryFinalizationStageStore):
            return MemoryJobResultUnitOfWorkFactory()
        return MemoryJobResultUnitOfWorkFactory(stage_store=stage_store)

    def get_job_scoped_recompute_factory(self) -> JobScopedRecomputeFactory:
        return DefaultJobScopedRecomputeFactory()

    def build_operational_result_promotion_service(
        self,
        *,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
    ) -> OperationalResultPromotionService:
        module = type(aisle_repo).__module__
        promotion_repo: OperationalJobPromotionRepository
        if module.startswith("src.infrastructure.repositories.sql_"):
            promotion_repo = SqlOperationalJobPromotionRepository(self._get_v3_sql_client())
        else:
            promotion_repo = MemoryOperationalJobPromotionRepository(
                aisle_repo=aisle_repo,
                job_repo=job_repo,
            )
        return OperationalResultPromotionService(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            promotion_repo=promotion_repo,
        )

    def get_operational_result_promotion_service(self) -> OperationalResultPromotionService:
        return self.build_operational_result_promotion_service(
            aisle_repo=self.get_aisle_repo(),
            job_repo=self.get_job_repo(),
        )

    def get_list_supplier_prompt_configs_use_case(self) -> ListSupplierPromptConfigsUseCase:
        return build_list_supplier_prompt_configs_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
            settings=self._settings,
        )

    def get_create_supplier_prompt_config_version_use_case(
        self,
    ) -> CreateSupplierPromptConfigVersionUseCase:
        return build_create_supplier_prompt_config_version_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
            clock=self.get_clock(),
            settings=self._settings,
        )

    def get_get_active_supplier_prompt_config_use_case(
        self,
    ) -> GetActiveSupplierPromptConfigUseCase:
        return build_get_active_supplier_prompt_config_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
            settings=self._settings,
        )

    def get_activate_supplier_prompt_config_version_use_case(
        self,
    ) -> ActivateSupplierPromptConfigVersionUseCase:
        return build_activate_supplier_prompt_config_version_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
        )

    def get_get_supplier_prompt_config_use_case(self) -> GetSupplierPromptConfigUseCase:
        return build_get_supplier_prompt_config_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            prompt_config_repo=self.get_supplier_prompt_config_repo(),
        )

    def get_list_supplier_extraction_profiles_use_case(
        self,
    ) -> ListSupplierExtractionProfilesUseCase:
        return build_list_supplier_extraction_profiles_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            profile_repo=self.get_supplier_extraction_profile_repo(),
        )

    def get_get_active_supplier_extraction_profile_use_case(
        self,
    ) -> GetActiveSupplierExtractionProfileUseCase:
        return build_get_active_supplier_extraction_profile_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            profile_repo=self.get_supplier_extraction_profile_repo(),
        )

    def get_get_supplier_extraction_profile_by_version_use_case(
        self,
    ) -> GetSupplierExtractionProfileByVersionUseCase:
        return build_get_supplier_extraction_profile_by_version_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            profile_repo=self.get_supplier_extraction_profile_repo(),
        )

    def get_create_supplier_extraction_profile_version_use_case(
        self,
    ) -> CreateSupplierExtractionProfileVersionUseCase:
        return build_create_supplier_extraction_profile_version_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            profile_repo=self.get_supplier_extraction_profile_repo(),
            clock=self.get_clock(),
        )

    def get_activate_supplier_extraction_profile_version_use_case(
        self,
    ) -> ActivateSupplierExtractionProfileVersionUseCase:
        return build_activate_supplier_extraction_profile_version_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            profile_repo=self.get_supplier_extraction_profile_repo(),
        )

    def get_clone_supplier_extraction_profile_use_case(
        self,
    ) -> CloneSupplierExtractionProfileUseCase:
        return build_clone_supplier_extraction_profile_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            profile_repo=self.get_supplier_extraction_profile_repo(),
            clock=self.get_clock(),
        )

    def get_list_supplier_reference_annotations_use_case(
        self,
    ) -> ListSupplierReferenceAnnotationsUseCase:
        return build_list_supplier_reference_annotations_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            reference_repo=self.get_supplier_reference_image_repo(),
            annotation_repo=self.get_supplier_reference_annotation_repo(),
        )

    def get_replace_supplier_reference_annotations_use_case(
        self,
    ) -> ReplaceSupplierReferenceAnnotationsUseCase:
        return build_replace_supplier_reference_annotations_use_case(
            client_repo=self.get_client_repo(),
            client_supplier_repo=self.get_client_supplier_repo(),
            reference_repo=self.get_supplier_reference_image_repo(),
            annotation_repo=self.get_supplier_reference_annotation_repo(),
            profile_repo=self.get_supplier_extraction_profile_repo(),
        )
