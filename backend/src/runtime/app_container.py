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
from src.application.ports.capture_repositories import (
    CaptureSessionConfirmIdempotencyRepository,
    CaptureSessionGroupRepository,
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.code_scan_repository import CodeScanRepository
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
    ReviewActionRepository,
    SourceAssetRepository,
    SupplierPromptConfigRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.services import ArtifactStorage, MetricsCalculator, WorkerLaunchService
from src.application.ports.stored_artifact_reader import StoredArtifactReader
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsUseCase,
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
    build_review_action_repository,
    build_source_asset_repository,
    build_supplier_prompt_config_repository,
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
        self._code_scan_repo: CodeScanRepository | None = None
        self._stored_artifact_reader: StoredArtifactReader | None = None
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
        self._position_repo = None
        self._product_record_repo = None
        self._evidence_repo = None
        self._review_action_repo = None
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
