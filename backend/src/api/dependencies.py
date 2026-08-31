"""
Central dependency provisioning for v3 API — Épica 2 + Épica 3.

Provides InventoryRepository, AisleRepository (SQL when sqlserver_enabled, else in-memory),
Clock, and use cases. Route modules depend on these; no infrastructure types in route code.

Fallback: when SQL is enabled but the initial connectivity probe fails, behavior is
controlled by ``V3_ALLOW_IN_MEMORY_FALLBACK`` and production-like runtime detection
(``APP_ENV`` / ``ENVIRONMENT`` / ``NODE_ENV`` — see ``runtime_environment.is_production_like_runtime``).
If the env var is set, only ``true`` / ``1`` / ``yes`` allow in-memory fallback. If **unset**,
production-like runtimes default to **fail-fast** (no ``MEMORY_FALLBACK``); non-production
defaults remain developer-friendly (fallback allowed). Set the env var explicitly in any
environment where the default is wrong for your deployment.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Depends

if TYPE_CHECKING:
    from src.application.use_cases.recovery.recover_aisle_processing import (
        RecoverAisleProcessingUseCase,
    )
    from src.application.use_cases.recovery.recover_stale_job import (
        RecoverStaleJobUseCase,
    )

from src.application.dto.access_principal import AccessPrincipal
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
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
    SourceAssetRepository,
    SupplierPromptConfigRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.services import MetricsCalculator, WorkerLaunchService
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.application.services.access_principal_factory import access_principal_from_auth_user
from src.application.services.aisle_identification_configuration_query import (
    AisleIdentificationConfigurationQuery,
)
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.analytics_query_service import AnalyticsQueryService
from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.operational_execution_config_resolver import (
    OperationalExecutionConfigResolver,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.aisles.activate_aisle import ActivateAisleUseCase
from src.application.use_cases.aisles.cancel_aisle_job import CancelAisleJobUseCase
from src.application.use_cases.aisles.create_aisle import CreateAisleUseCase
from src.application.use_cases.aisles.deactivate_aisle import DeactivateAisleUseCase
from src.application.use_cases.aisles.delete_aisle_source_asset import DeleteAisleSourceAssetUseCase
from src.application.use_cases.aisles.get_aisle_merge_results import (
    GetAisleMergeResultsUseCase,
)
from src.application.use_cases.aisles.get_aisle_processing_status import (
    GetAisleProcessingStatusUseCase,
)
from src.application.use_cases.aisles.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.aisles.list_aisle_jobs import ListAisleJobsUseCase
from src.application.use_cases.aisles.list_aisles_by_inventory import ListAislesByInventoryUseCase
from src.application.use_cases.aisles.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.aisles.promote_aisle_operational_job import (
    PromoteAisleOperationalJobUseCase,
)
from src.application.use_cases.aisles.resolve_aisle_job_for_inventory_read import (
    ResolveAisleJobForInventoryReadUseCase,
)
from src.application.use_cases.aisles.retry_aisle_job import RetryAisleJobUseCase
from src.application.use_cases.aisles.run_aisle_merge import RunAisleMergeUseCase
from src.application.use_cases.aisles.start_aisle_processing import StartAisleProcessingUseCase
from src.application.use_cases.aisles.update_aisle_code import UpdateAisleCodeUseCase
from src.application.use_cases.aisles.upload_aisle_assets import UploadAisleAssetsUseCase
from src.application.use_cases.analytics.compare_aisle_runs import CompareAisleRunsUseCase
from src.application.use_cases.analytics.compare_many_aisle_runs import CompareManyAisleRunsUseCase
from src.application.use_cases.analytics.export_aisle_benchmark import (
    ExportAisleBenchmarkCompareCsvUseCase,
    ExportAisleBenchmarkRunCsvUseCase,
)
from src.application.use_cases.clients.create_client import CreateClientUseCase
from src.application.use_cases.clients.get_client import GetClientUseCase
from src.application.use_cases.clients.list_clients import ListClientsUseCase
from src.application.use_cases.clients.update_client import UpdateClientUseCase
from src.application.use_cases.code_scans.export_aisle_code_scans import ExportAisleCodeScansUseCase
from src.application.use_cases.code_scans.get_aisle_code_scan_review_signals import (
    GetAisleCodeScanReviewSignalsUseCase,
)
from src.application.use_cases.code_scans.list_aisle_code_scans import ListAisleCodeScansUseCase
from src.application.use_cases.code_scans.match_aisle_code_scan_detections import (
    MatchAisleCodeScanDetectionsUseCase,
)
from src.application.use_cases.code_scans.run_aisle_code_scan import RunAisleCodeScanUseCase
from src.application.use_cases.code_scans.summarize_aisle_code_scans import (
    SummarizeAisleCodeScansUseCase,
)
from src.application.use_cases.inventories.create_inventory import CreateInventoryUseCase
from src.application.use_cases.inventories.export_inventory_business import (
    ExportAisleBusinessCsvUseCase,
    ExportInventoryPackageZipUseCase,
    ExportInventorySummaryCsvUseCase,
)
from src.application.use_cases.inventories.export_inventory_results import (
    ExportAisleResultsCsvUseCase,
    ExportInventoryResultsUseCase,
)
from src.application.use_cases.inventories.get_inventory import GetInventoryUseCase
from src.application.use_cases.inventories.get_inventory_metrics import GetInventoryMetricsUseCase
from src.application.use_cases.inventories.list_inventories import ListInventoriesUseCase
from src.application.use_cases.inventories.list_inventory_list_items import (
    ListInventoryListItemsUseCase,
)
from src.application.use_cases.inventories.soft_delete_inventories import (
    SoftDeleteInventoriesUseCase,
)
from src.application.use_cases.inventories.update_inventory_name import UpdateInventoryNameUseCase
from src.application.use_cases.positions.confirm_position import ConfirmPositionUseCase
from src.application.use_cases.positions.delete_position import DeletePositionUseCase
from src.application.use_cases.positions.get_position_code_scan_evidence import (
    GetPositionCodeScanEvidenceUseCase,
)
from src.application.use_cases.positions.get_position_detail import GetPositionDetailUseCase
from src.application.use_cases.positions.list_aisle_positions import ListAislePositionsUseCase
from src.application.use_cases.positions.list_review_queue import ListReviewQueueUseCase
from src.application.use_cases.positions.mark_position_image_mismatch import (
    MarkPositionImageMismatchUseCase,
)
from src.application.use_cases.positions.mark_position_unknown import MarkPositionUnknownUseCase
from src.application.use_cases.positions.update_position_code import UpdatePositionCodeUseCase
from src.application.use_cases.positions.update_product_quantity import UpdateProductQuantityUseCase
from src.application.use_cases.positions.update_product_sku import UpdateProductSkuUseCase
from src.application.use_cases.suppliers.create_client_supplier import CreateClientSupplierUseCase
from src.application.use_cases.suppliers.get_client_supplier import GetClientSupplierUseCase
from src.application.use_cases.suppliers.list_client_suppliers import ListClientSuppliersUseCase
from src.application.use_cases.suppliers.manage_supplier_prompt_configs import (
    ActivateSupplierPromptConfigVersionUseCase,
    CreateSupplierPromptConfigVersionUseCase,
    GetActiveSupplierPromptConfigUseCase,
    GetSupplierPromptConfigUseCase,
    ListSupplierPromptConfigsUseCase,
)
from src.application.use_cases.suppliers.manage_supplier_reference_images import (
    DeleteSupplierReferenceImageUseCase,
    GetSupplierReferenceImageUseCase,
)
from src.application.use_cases.suppliers.upload_supplier_reference_images import (
    ListSupplierReferenceImagesUseCase,
    UploadSupplierReferenceImagesUseCase,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.runtime.app_container import get_app_container
from src.runtime.v3_deps import (
    get_aisle_location_label_repo,
    get_aisle_location_repo,
    get_aisle_repo,
    get_analytics_repo,
    get_capture_session_confirm_repo,
    get_capture_session_group_repo,
    get_capture_session_item_repo,
    get_capture_session_repo,
    get_client_repo,
    get_client_supplier_repo,
    get_clock,
    get_code_scan_repo,
    get_evidence_repo,
    get_final_count_repo,
    get_inventory_repo,
    get_job_repo,
    get_metrics_calculator,
    get_mobile_preliminary_detection_repo,
    get_ordered_capture_processing_reservation,
    get_ordered_capture_session_repo,
    get_position_repo,
    get_preliminary_detection_reconciliation_repo,
    get_product_record_repo,
    get_recompute_consolidated_counts_use_case,
    get_review_action_repo,
    get_source_asset_repo,
    get_supplier_prompt_config_repo,
    get_supplier_reference_image_repo,
    get_worker_launch_service,
)
from src.runtime.v3_deps import (
    get_artifact_manifest_store as _get_artifact_manifest_store,
)
from src.runtime.v3_deps import (
    get_artifact_publication_outbox_store as _get_artifact_publication_outbox_store,
)
from src.runtime.v3_deps import (
    get_finalization_assessment_service as _get_finalization_assessment_service,
)
from src.runtime.v3_deps import (
    get_result_evidence_repo as _get_result_evidence_repo,
)

logger = logging.getLogger(__name__)


def get_artifact_storage():
    """Return configured artifact storage adapter (local or S3) via the app composition root."""
    return get_app_container().get_artifact_storage()


def get_worker_launch_service_dep() -> WorkerLaunchService:
    return get_worker_launch_service()


def get_job_stale_reconciler(
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
) -> JobStaleReconciler:
    from src.config import load_settings

    settings = load_settings()
    outbox_store = None
    try:
        outbox_store = _get_artifact_publication_outbox_store()
    except Exception:
        outbox_store = None
    return JobStaleReconciler(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        clock=clock,
        stale_after_seconds=int(getattr(settings, "worker_stale_running_timeout_sec", 0) or 0),
        artifact_publication_outbox=outbox_store,
    )


def get_finalization_assessment_service() -> FinalizationAssessmentService:
    return _get_finalization_assessment_service()


def get_artifact_publication_outbox_store():
    return _get_artifact_publication_outbox_store()


def get_artifact_manifest_store():
    return _get_artifact_manifest_store()


def get_supplier_extraction_profile_repo() -> SupplierExtractionProfileRepository:
    return get_app_container().get_supplier_extraction_profile_repo()


def get_client_supplier_label_profile_repo():

    return get_app_container().get_client_supplier_label_profile_repo()


def get_result_evidence_repo():
    return _get_result_evidence_repo()


def get_result_evidence_query_service(
    result_evidence_repo=Depends(get_result_evidence_repo),
    source_asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    manifest_store=Depends(get_artifact_manifest_store),
    artifact_storage=Depends(get_artifact_storage),
):
    from src.api.services.v3_stored_artifact_access import resolve_source_asset_image_display
    from src.application.services.result_evidence_query_service import ResultEvidenceQueryService

    return ResultEvidenceQueryService(
        result_evidence_repo=result_evidence_repo,
        source_asset_repo=source_asset_repo,
        manifest_store=manifest_store,
        artifact_store=artifact_storage,
        image_url_resolver=resolve_source_asset_image_display,
    )


def get_operational_execution_config_resolver() -> OperationalExecutionConfigResolver:
    return OperationalExecutionConfigResolver()


def require_inventory_client_scope(
    inventory_id: str,
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    user: AuthUser = Depends(get_current_admin),
) -> AccessPrincipal:
    """FastAPI dependency: enforce actor→client→inventory; return AccessPrincipal.

    Raised as a **dependency** (before the route body runs), so failures here are not
    caught by a route's own ``try/except reraise_if_mapped``. Map them explicitly —
    otherwise an unmapped ``InventoryNotFoundError`` raised during dependency resolution
    escapes FastAPI's registered exception handlers and surfaces as a 500, not the
    intended 404 (verified: ``ServerErrorMiddleware`` sits outside ``ExceptionMiddleware``,
    so only ``StructuredApiHttpError``/``HTTPException`` raised here become the documented
    client-facing status).
    """
    from src.api.errors import reraise_if_mapped

    principal = access_principal_from_auth_user(user)
    try:
        InventoryAccessPolicy(inventory_repo).require_inventory(inventory_id, principal)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return principal


def get_access_principal(
    user: AuthUser = Depends(get_current_admin),
) -> AccessPrincipal:
    """FastAPI dependency: AuthUser → AccessPrincipal (no inventory scope check)."""
    return access_principal_from_auth_user(user)


def get_inventory_access_policy(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
) -> InventoryAccessPolicy:
    return InventoryAccessPolicy(inventory_repo, aisle_repo=aisle_repo)


def get_capture_session_access_policy(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    capture_session_repo=Depends(get_capture_session_repo),
) -> InventoryAccessPolicy:
    return InventoryAccessPolicy(
        inventory_repo,
        aisle_repo=aisle_repo,
        capture_session_repo=capture_session_repo,
    )


def require_capture_session_upload_scope(
    inventory_id: str,
    session_id: str,
    aisle_id: str | None = None,
    access_policy: InventoryAccessPolicy = Depends(get_capture_session_access_policy),
    user: AuthUser = Depends(get_current_admin),
) -> AccessPrincipal:
    """Validate inventory→session→aisle hierarchy before multipart staging spool.

    Runs as a **dependency**, ahead of ``files: File(...)`` in the route signature, so a
    denial here means Starlette/FastAPI never invokes the route body's own upload-spool
    call. Domain errors (``InventoryNotFoundError`` / ``CaptureSessionNotFoundError`` /
    ``AisleNotFoundError`` / ``CaptureSessionNotAcceptingUploadsError``) must be mapped to
    HTTP here explicitly: raised unmapped from a dependency, they bypass every route's
    ``try/except reraise_if_mapped`` and reach only the global ``Exception`` handler,
    which is wired to Starlette's outer ``ServerErrorMiddleware`` — producing a 500
    instead of the documented 404/409, even though the security check itself ran correctly.
    """
    from src.api.errors import reraise_if_mapped

    principal = access_principal_from_auth_user(user)
    try:
        access_policy.require_capture_session_for_staging_upload(
            inventory_id=inventory_id,
            session_id=session_id,
            principal=principal,
            aisle_id=aisle_id,
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return principal


def get_create_inventory_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
    operational_resolver: OperationalExecutionConfigResolver = Depends(
        get_operational_execution_config_resolver
    ),
) -> CreateInventoryUseCase:
    from src.config import load_settings as _load_settings

    return CreateInventoryUseCase(
        inventory_repo=repo,
        client_repo=client_repo,
        clock=clock,
        operational_resolver=operational_resolver,
        settings_loader=_load_settings,
    )


def get_update_inventory_name_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
    clock: Clock = Depends(get_clock),
) -> UpdateInventoryNameUseCase:
    return UpdateInventoryNameUseCase(inventory_repo=repo, clock=clock)


def get_soft_delete_inventories_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
    clock: Clock = Depends(get_clock),
) -> SoftDeleteInventoriesUseCase:
    return SoftDeleteInventoriesUseCase(inventory_repo=repo, clock=clock)


def get_create_client_use_case(
    repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> CreateClientUseCase:
    return CreateClientUseCase(client_repo=repo, clock=clock)


def get_update_client_use_case(
    repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> UpdateClientUseCase:
    return UpdateClientUseCase(client_repo=repo, clock=clock)


def get_create_client_supplier_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    clock: Clock = Depends(get_clock),
) -> CreateClientSupplierUseCase:
    return CreateClientSupplierUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        clock=clock,
    )


def get_list_inventories_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
) -> ListInventoriesUseCase:
    return ListInventoriesUseCase(inventory_repo=repo)


def get_list_clients_use_case(
    repo: ClientRepository = Depends(get_client_repo),
) -> ListClientsUseCase:
    return ListClientsUseCase(client_repo=repo)


def get_list_client_suppliers_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
) -> ListClientSuppliersUseCase:
    return ListClientSuppliersUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
    )


def get_list_inventory_list_items_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> ListInventoryListItemsUseCase:
    return ListInventoryListItemsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        client_repo=client_repo,
    )


def get_result_context_resolver(
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
) -> ResultContextResolver:
    return ResultContextResolver(job_repo=job_repo, position_repo=position_repo)


def get_get_inventory_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
) -> GetInventoryUseCase:
    return GetInventoryUseCase(inventory_repo=repo)


def get_get_client_use_case(
    repo: ClientRepository = Depends(get_client_repo),
) -> GetClientUseCase:
    return GetClientUseCase(client_repo=repo)


def get_get_client_supplier_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
) -> GetClientSupplierUseCase:
    return GetClientSupplierUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
    )


def get_export_inventory_results_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
) -> ExportInventoryResultsUseCase:
    return ExportInventoryResultsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        reconciliation_repo=get_app_container().get_position_reconciliation_repo(),
        override_repo=get_app_container().get_manual_position_override_repo(),
        label_repo=get_app_container().get_client_position_label_repo(),
    )


def get_export_aisle_results_csv_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
) -> ExportAisleResultsCsvUseCase:
    return ExportAisleResultsCsvUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        reconciliation_repo=get_app_container().get_position_reconciliation_repo(),
        override_repo=get_app_container().get_manual_position_override_repo(),
        label_repo=get_app_container().get_client_position_label_repo(),
    )


def get_export_inventory_summary_csv_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> ExportInventorySummaryCsvUseCase:
    return ExportInventorySummaryCsvUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        job_repo=job_repo,
    )


def get_export_inventory_package_zip_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> ExportInventoryPackageZipUseCase:
    return ExportInventoryPackageZipUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        job_repo=job_repo,
    )


def get_export_aisle_business_csv_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
) -> ExportAisleBusinessCsvUseCase:
    return ExportAisleBusinessCsvUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
    )


def get_get_inventory_metrics_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    metrics_calculator: MetricsCalculator = Depends(get_metrics_calculator),
) -> GetInventoryMetricsUseCase:
    return GetInventoryMetricsUseCase(
        inventory_repo=inventory_repo,
        metrics_calculator=metrics_calculator,
    )


def get_inventory_status_reconciler(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
) -> InventoryStatusReconciler:
    return InventoryStatusReconciler(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        clock=clock,
    )


def get_aisle_review_lifecycle_sync(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    clock: Clock = Depends(get_clock),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
) -> AisleReviewLifecycleSync:
    return AisleReviewLifecycleSync(
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        clock=clock,
        status_reconciler=status_reconciler,
    )


def get_create_aisle_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    clock: Clock = Depends(get_clock),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
) -> CreateAisleUseCase:
    return CreateAisleUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=client_supplier_repo,
        clock=clock,
        status_reconciler=status_reconciler,
    )


def get_aisle_identification_configuration_query(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> AisleIdentificationConfigurationQuery:
    return AisleIdentificationConfigurationQuery(
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
        client_repo=client_repo,
    )


def get_update_aisle_code_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
) -> UpdateAisleCodeUseCase:
    return UpdateAisleCodeUseCase(aisle_repo=aisle_repo, clock=clock)


def get_deactivate_aisle_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    clock: Clock = Depends(get_clock),
    stale_reconciler: JobStaleReconciler = Depends(get_job_stale_reconciler),
) -> DeactivateAisleUseCase:
    return DeactivateAisleUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
        stale_reconciler=stale_reconciler,
    )


def get_activate_aisle_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
) -> ActivateAisleUseCase:
    return ActivateAisleUseCase(aisle_repo=aisle_repo, clock=clock)


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
    position_repo: PositionRepository = Depends(get_position_repo),
    source_asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    container=Depends(get_app_container),
) -> ListAislesWithStatusUseCase:
    return ListAislesWithStatusUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        source_asset_repo=source_asset_repo,
        result_context_resolver=result_context_resolver,
        client_supplier_repo=client_supplier_repo,
        local_csv_result_writer=container.get_local_csv_result_writer(),
    )


def get_aisle_job_launch_service(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    worker_launch_service: WorkerLaunchService = Depends(get_worker_launch_service_dep),
    clock: Clock = Depends(get_clock),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
) -> AisleJobLaunchService:
    return AisleJobLaunchService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        worker_launch_service=worker_launch_service,
        clock=clock,
        status_reconciler=status_reconciler,
    )


def get_start_aisle_processing_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    launch_service: AisleJobLaunchService = Depends(get_aisle_job_launch_service),
    stale_reconciler: JobStaleReconciler = Depends(get_job_stale_reconciler),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    client_repo: ClientRepository = Depends(get_client_repo),
    extraction_profile_repo: SupplierExtractionProfileRepository = Depends(
        get_supplier_extraction_profile_repo
    ),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    supplier_prompt_config_repo: SupplierPromptConfigRepository = Depends(
        get_supplier_prompt_config_repo
    ),
    label_profile_repo=Depends(get_client_supplier_label_profile_repo),
    ordered_session_repo=Depends(get_ordered_capture_session_repo),
    ordered_processing_reservation=Depends(get_ordered_capture_processing_reservation),
) -> StartAisleProcessingUseCase:
    return StartAisleProcessingUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=job_repo,
        launch_service=launch_service,
        stale_reconciler=stale_reconciler,
        access_policy=access_policy,
        client_repo=client_repo,
        extraction_profile_repo=extraction_profile_repo,
        client_supplier_repo=client_supplier_repo,
        supplier_prompt_config_repo=supplier_prompt_config_repo,
        label_profile_repo=label_profile_repo,
        ordered_session_repo=ordered_session_repo,
        ordered_processing_reservation=ordered_processing_reservation,
    )


def get_get_aisle_processing_status_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    stale_reconciler: JobStaleReconciler = Depends(get_job_stale_reconciler),
) -> GetAisleProcessingStatusUseCase:
    return GetAisleProcessingStatusUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        stale_reconciler=stale_reconciler,
    )


def get_cancel_aisle_job_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    clock: Clock = Depends(get_clock),
) -> CancelAisleJobUseCase:
    return CancelAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
    )


def get_recover_stale_job_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    launch_service: AisleJobLaunchService = Depends(get_aisle_job_launch_service),
    clock: Clock = Depends(get_clock),
) -> RecoverStaleJobUseCase:
    from src.application.use_cases.recovery.recover_stale_job import RecoverStaleJobUseCase

    return RecoverStaleJobUseCase(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        launch_service=launch_service,
        clock=clock,
    )


def get_recover_aisle_processing_use_case(
    status_use_case: GetAisleProcessingStatusUseCase = Depends(
        get_get_aisle_processing_status_use_case
    ),
    recover_stale: RecoverStaleJobUseCase = Depends(get_recover_stale_job_use_case),
    cancel_job: CancelAisleJobUseCase = Depends(get_cancel_aisle_job_use_case),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    clock: Clock = Depends(get_clock),
) -> RecoverAisleProcessingUseCase:
    from src.application.use_cases.recovery.recover_aisle_processing import (
        RecoverAisleProcessingUseCase,
    )

    return RecoverAisleProcessingUseCase(
        status_use_case=status_use_case,
        recover_stale=recover_stale,
        cancel_job=cancel_job,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
    )


def get_retry_aisle_job_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    launch_service: AisleJobLaunchService = Depends(get_aisle_job_launch_service),
    stale_reconciler: JobStaleReconciler = Depends(get_job_stale_reconciler),
) -> RetryAisleJobUseCase:
    return RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=launch_service,
        stale_reconciler=stale_reconciler,
    )


def get_upload_aisle_assets_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    ordered_session_repo=Depends(get_ordered_capture_session_repo),
) -> UploadAisleAssetsUseCase:
    from src.application.services.upload_request_limits import UploadRequestLimitPolicy
    from src.config import load_settings

    return UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=artifact_storage,
        clock=clock,
        status_reconciler=status_reconciler,
        access_policy=access_policy,
        upload_policy=UploadRequestLimitPolicy.from_settings(load_settings()),
        ordered_session_repo=ordered_session_repo,
    )


def get_list_aisle_assets_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
) -> ListAisleAssetsUseCase:
    return ListAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        access_policy=access_policy,
    )


def get_upsert_preliminary_detection_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    preliminary_repo=Depends(get_mobile_preliminary_detection_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.aisles.upsert_preliminary_detection import (
        UpsertPreliminaryDetectionUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    return UpsertPreliminaryDetectionUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        preliminary_repo=preliminary_repo,
        clock=clock,
        enabled=bool(
            getattr(settings, "server_preliminary_detection_ingest_enabled", False)
        ),
    )


def get_persist_authoritative_local_code_scan_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    clock: Clock = Depends(get_clock),
    user: AuthUser = Depends(get_current_admin),
):
    from src.application.use_cases.aisles.persist_authoritative_local_code_scan import (
        PersistAuthoritativeLocalCodeScanResultUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    c = get_app_container()
    return PersistAuthoritativeLocalCodeScanResultUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        authoritative_repo=c.get_authoritative_local_code_scan_repo(),
        clock=clock,
        enabled=bool(
            getattr(settings, "server_authoritative_local_code_scan_ingest_enabled", False)
        ),
        authenticated_user_id=str(getattr(user, "id", "") or ""),
    )


def get_preview_local_csv_import_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.inventories.manage_local_csv_import import (
        PreviewLocalCsvImport,
    )
    from src.config import load_settings

    settings = load_settings()
    return PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=get_app_container().get_local_csv_import_repo(),
        clock=clock,
        enabled=bool(getattr(settings, "server_csv_import_enabled", False)),
    )


def get_confirm_local_csv_import_use_case(
    clock: Clock = Depends(get_clock),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
):
    from src.application.services.local_csv_position_materializer import (
        LocalCsvPositionMaterializer,
    )
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.services.product_labels.issued_product_label_resolver import (
        IssuedProductLabelResolver,
    )
    from src.application.use_cases.inventories.manage_local_csv_import import (
        ConfirmLocalCsvImport,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=settings.positioning_label_hmac_secret or None,
            key_version=int(settings.positioning_label_hmac_key_version),
            previous_secrets=parse_previous_secrets(
                settings.positioning_label_hmac_previous_secrets
            ),
            required=bool(settings.positioning_label_signing_required),
        )
    )
    return ConfirmLocalCsvImport(
        import_repo=container.get_local_csv_import_repo(),
        result_writer=container.get_local_csv_result_writer(),
        clock=clock,
        enabled=bool(getattr(settings, "server_csv_import_enabled", False)),
        position_materializer=LocalCsvPositionMaterializer(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            counted_product_label_repo=container.get_counted_product_label_repo(),
            issued_label_resolver=IssuedProductLabelResolver(
                issued_repo=container.get_issued_product_label_repo()
            ),
            inventory_repo=inventory_repo,
            client_position_label_repo=container.get_client_position_label_repo(),
            positioning_signing=signing if signing.can_sign else None,
        ),
        aisle_repo=aisle_repo,
        status_reconciler=status_reconciler,
    )


def get_get_local_csv_import_use_case():
    from src.application.use_cases.inventories.manage_local_csv_import import GetLocalCsvImport
    from src.config import load_settings

    settings = load_settings()
    return GetLocalCsvImport(
        import_repo=get_app_container().get_local_csv_import_repo(),
        enabled=bool(getattr(settings, "server_csv_import_enabled", False)),
    )


def get_preview_local_inventory_package_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
):
    from pathlib import Path

    from src.application.use_cases.inventories.manage_local_csv_import import (
        PreviewLocalCsvImport,
    )
    from src.application.use_cases.inventories.manage_local_inventory_package import (
        PreviewLocalInventoryPackage,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    csv_repo = container.get_local_csv_import_repo()
    csv_preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=csv_repo,
        clock=clock,
        enabled=bool(getattr(settings, "server_csv_import_enabled", False))
        or bool(getattr(settings, "server_local_inventory_package_enabled", False)),
    )
    staging_root = Path(getattr(settings, "output_dir", "/tmp")) / "local_inventory_packages"
    return PreviewLocalInventoryPackage(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=container.get_local_inventory_package_repo(),
        csv_preview=csv_preview,
        clock=clock,
        enabled=bool(getattr(settings, "server_local_inventory_package_enabled", False)),
        staging_root=staging_root,
    )


def get_confirm_local_inventory_package_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    artifact_storage=Depends(get_artifact_storage),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    clock: Clock = Depends(get_clock),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
):
    from src.application.services.aisle_source_asset_materializer import (
        AisleSourceAssetMaterializer,
    )
    from src.application.services.local_csv_position_materializer import (
        LocalCsvPositionMaterializer,
    )
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.services.product_labels.issued_product_label_resolver import (
        IssuedProductLabelResolver,
    )
    from src.application.use_cases.inventories.manage_local_inventory_package import (
        ConfirmLocalInventoryPackage,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    materializer = AisleSourceAssetMaterializer(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=artifact_storage,
        status_reconciler=status_reconciler,
    )
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=settings.positioning_label_hmac_secret or None,
            key_version=int(settings.positioning_label_hmac_key_version),
            previous_secrets=parse_previous_secrets(
                settings.positioning_label_hmac_previous_secrets
            ),
            required=bool(settings.positioning_label_signing_required),
        )
    )
    return ConfirmLocalInventoryPackage(
        package_repo=container.get_local_inventory_package_repo(),
        result_writer=container.get_local_csv_result_writer(),
        materializer=materializer,
        aisle_repo=aisle_repo,
        clock=clock,
        enabled=bool(getattr(settings, "server_local_inventory_package_enabled", False)),
        position_materializer=LocalCsvPositionMaterializer(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            counted_product_label_repo=container.get_counted_product_label_repo(),
            issued_label_resolver=IssuedProductLabelResolver(
                issued_repo=container.get_issued_product_label_repo()
            ),
            inventory_repo=inventory_repo,
            client_position_label_repo=container.get_client_position_label_repo(),
            positioning_signing=signing if signing.can_sign else None,
        ),
    )


def get_get_local_inventory_package_use_case():
    from src.application.use_cases.inventories.manage_local_inventory_package import (
        GetLocalInventoryPackage,
    )
    from src.config import load_settings

    settings = load_settings()
    return GetLocalInventoryPackage(
        package_repo=get_app_container().get_local_inventory_package_repo(),
        enabled=bool(getattr(settings, "server_local_inventory_package_enabled", False)),
    )


def _dinamic_scanner_txt_import_enabled(settings) -> bool:
    return bool(getattr(settings, "server_dinamic_scanner_txt_import_enabled", False))


def _csv_import_pipeline_enabled(settings) -> bool:
    return (
        bool(getattr(settings, "server_csv_import_enabled", False))
        or bool(getattr(settings, "server_local_inventory_package_enabled", False))
        or _dinamic_scanner_txt_import_enabled(settings)
    )


def get_preview_dinamic_scanner_txt_import_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    clock: Clock = Depends(get_clock),
    create_aisle: CreateAisleUseCase = Depends(get_create_aisle_use_case),
):
    from src.application.services.dinamic_scanner_aisle_resolver import DinamicScannerAisleResolver
    from src.application.use_cases.inventories.manage_dinamic_scanner_txt_import import (
        PreviewDinamicScannerTxtImport,
    )
    from src.application.use_cases.inventories.manage_local_csv_import import (
        PreviewLocalCsvImport,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    csv_preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=container.get_local_csv_import_repo(),
        clock=clock,
        enabled=_csv_import_pipeline_enabled(settings),
    )
    aisle_resolver = DinamicScannerAisleResolver(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=client_supplier_repo,
        create_aisle=create_aisle,
    )
    return PreviewDinamicScannerTxtImport(
        inventory_repo=inventory_repo,
        aisle_resolver=aisle_resolver,
        import_repo=container.get_local_csv_import_repo(),
        csv_preview=csv_preview,
        clock=clock,
        enabled=_dinamic_scanner_txt_import_enabled(settings),
        max_lines=int(getattr(settings, "server_dinamic_scanner_txt_max_lines", 50_000)),
        max_line_length=int(
            getattr(settings, "server_dinamic_scanner_txt_max_line_length", 512)
        ),
    )


def get_confirm_dinamic_scanner_txt_import_use_case(
    clock: Clock = Depends(get_clock),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    create_aisle: CreateAisleUseCase = Depends(get_create_aisle_use_case),
):
    from src.application.services.dinamic_scanner_aisle_resolver import DinamicScannerAisleResolver
    from src.application.services.local_csv_position_materializer import (
        LocalCsvPositionMaterializer,
    )
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.services.product_labels.issued_product_label_resolver import (
        IssuedProductLabelResolver,
    )
    from src.application.use_cases.inventories.manage_dinamic_scanner_txt_import import (
        ConfirmDinamicScannerTxtImport,
    )
    from src.application.use_cases.inventories.manage_local_csv_import import (
        ConfirmLocalCsvImport,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=settings.positioning_label_hmac_secret or None,
            key_version=int(settings.positioning_label_hmac_key_version),
            previous_secrets=parse_previous_secrets(
                settings.positioning_label_hmac_previous_secrets
            ),
            required=bool(settings.positioning_label_signing_required),
        )
    )
    csv_confirm = ConfirmLocalCsvImport(
        import_repo=container.get_local_csv_import_repo(),
        result_writer=container.get_local_csv_result_writer(),
        clock=clock,
        enabled=_csv_import_pipeline_enabled(settings),
        position_materializer=LocalCsvPositionMaterializer(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            counted_product_label_repo=container.get_counted_product_label_repo(),
            issued_label_resolver=IssuedProductLabelResolver(
                issued_repo=container.get_issued_product_label_repo()
            ),
            inventory_repo=inventory_repo,
            client_position_label_repo=container.get_client_position_label_repo(),
            positioning_signing=signing if signing.can_sign else None,
        ),
        aisle_repo=aisle_repo,
        status_reconciler=status_reconciler,
    )
    aisle_resolver = DinamicScannerAisleResolver(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=client_supplier_repo,
        create_aisle=create_aisle,
    )
    return ConfirmDinamicScannerTxtImport(
        import_repo=container.get_local_csv_import_repo(),
        aisle_resolver=aisle_resolver,
        csv_confirm=csv_confirm,
        enabled=_dinamic_scanner_txt_import_enabled(settings),
    )


def get_evaluate_authoritative_aisle_readiness(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
):
    from src.application.services.evaluate_authoritative_aisle_readiness import (
        EvaluateAuthoritativeAisleReadiness,
    )
    from src.config import load_settings

    del aisle_repo  # scope validated by callers / finalize
    settings = load_settings()
    c = get_app_container()
    return EvaluateAuthoritativeAisleReadiness(
        asset_repo=asset_repo,
        authoritative_repo=c.get_authoritative_local_code_scan_repo(),
        finalization_repo=c.get_authoritative_aisle_finalization_repo(),
        position_repo=c.get_position_repo(),
        enabled=bool(
            getattr(settings, "server_authoritative_aisle_finalization_enabled", False)
        ),
    )


def get_finalize_authoritative_aisle_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.services.evaluate_authoritative_aisle_readiness import (
        EvaluateAuthoritativeAisleReadiness,
    )
    from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
    from src.application.use_cases.aisles.finalize_authoritative_aisle import (
        FinalizeAuthoritativeAisle,
    )
    from src.config import load_settings

    settings = load_settings()
    c = get_app_container()
    enabled = bool(
        getattr(settings, "server_authoritative_aisle_finalization_enabled", False)
    )
    readiness = EvaluateAuthoritativeAisleReadiness(
        asset_repo=asset_repo,
        authoritative_repo=c.get_authoritative_local_code_scan_repo(),
        finalization_repo=c.get_authoritative_aisle_finalization_repo(),
        position_repo=c.get_position_repo(),
        enabled=enabled,
    )
    return FinalizeAuthoritativeAisle(
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
        asset_repo=asset_repo,
        authoritative_repo=c.get_authoritative_local_code_scan_repo(),
        finalization_repo=c.get_authoritative_aisle_finalization_repo(),
        readiness=readiness,
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            clock=clock,
        ),
        clock=clock,
        position_repo=c.get_position_repo(),
        enabled=enabled,
    )


def get_reconcile_preliminary_detections_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    preliminary_repo=Depends(get_mobile_preliminary_detection_repo),
    reconciliation_repo=Depends(get_preliminary_detection_reconciliation_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.aisles.reconcile_preliminary_detections import (
        EnqueuePreliminaryReconciliationsUseCase,
        ProcessPreliminaryReconciliationsUseCase,
        ReconcilePreliminaryDetectionsUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    enabled = bool(getattr(settings, "server_preliminary_reconciliation_enabled", False))
    metrics_enabled = bool(
        getattr(settings, "preliminary_reconciliation_metrics_enabled", False)
    )
    c = get_app_container()
    enqueue = EnqueuePreliminaryReconciliationsUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        preliminary_repo=preliminary_repo,
        reconciliation_repo=reconciliation_repo,
        job_source_asset_repo=c.get_job_source_asset_repo(),
        enabled=enabled,
        clock=clock,
    )
    process = ProcessPreliminaryReconciliationsUseCase(
        job_repo=job_repo,
        preliminary_repo=preliminary_repo,
        reconciliation_repo=reconciliation_repo,
        state_repo=c.get_job_asset_processing_state_repo(),
        attempt_repo=c.get_processing_attempt_repo(),
        job_source_asset_repo=c.get_job_source_asset_repo(),
        enabled=enabled,
        metrics_enabled=metrics_enabled,
        clock=clock,
    )
    return ReconcilePreliminaryDetectionsUseCase(
        enqueue=enqueue,
        process=process,
        process_inline_limit=0,
    )


def get_process_preliminary_reconciliations_use_case():
    from src.application.use_cases.aisles.reconcile_preliminary_detections import (
        ProcessPreliminaryReconciliationsUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    c = get_app_container()
    return ProcessPreliminaryReconciliationsUseCase(
        job_repo=c.get_job_repo(),
        preliminary_repo=c.get_mobile_preliminary_detection_repo(),
        reconciliation_repo=c.get_preliminary_detection_reconciliation_repo(),
        state_repo=c.get_job_asset_processing_state_repo(),
        attempt_repo=c.get_processing_attempt_repo(),
        job_source_asset_repo=c.get_job_source_asset_repo(),
        enabled=bool(getattr(settings, "server_preliminary_reconciliation_enabled", False)),
        metrics_enabled=bool(
            getattr(settings, "preliminary_reconciliation_metrics_enabled", False)
        ),
        clock=c.get_clock(),
    )


def get_list_preliminary_reconciliations_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    reconciliation_repo=Depends(get_preliminary_detection_reconciliation_repo),
):
    from src.application.use_cases.aisles.list_preliminary_reconciliations import (
        ListPreliminaryReconciliationsUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    return ListPreliminaryReconciliationsUseCase(
        aisle_repo=aisle_repo,
        reconciliation_repo=reconciliation_repo,
        enabled=bool(
            getattr(settings, "server_preliminary_reconciliation_enabled", False)
        ),
    )


def get_delete_aisle_source_asset_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
) -> DeleteAisleSourceAssetUseCase:
    return DeleteAisleSourceAssetUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=job_repo,
        artifact_storage=artifact_storage,
        clock=clock,
        status_reconciler=status_reconciler,
        access_policy=access_policy,
    )


def get_code_scanner():
    """Production aisle code scanner (pyzbar). Maps missing libzbar to structured 503."""
    from src.api.errors import mapped_http_exception
    from src.application.errors import CodeScanScannerUnavailableError
    from src.infrastructure.code_scanning.pyzbar_code_scanner import (
        PyzbarCodeScanner,
        PyzbarUnavailableError,
    )

    try:
        return PyzbarCodeScanner()
    except PyzbarUnavailableError as exc:
        unavailable = CodeScanScannerUnavailableError(
            "Code scan engine is unavailable. Install pyzbar and system libzbar0."
        )
        mapped = mapped_http_exception(unavailable)
        if mapped is not None:
            raise mapped from exc
        raise unavailable from exc


def get_source_asset_content_reader(
    artifact_storage=Depends(get_artifact_storage),
):
    from src.infrastructure.code_scanning.artifact_store_source_asset_content_reader import (
        ArtifactStoreSourceAssetContentReader,
    )

    return ArtifactStoreSourceAssetContentReader(artifact_storage)


def get_match_aisle_code_scan_detections_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    code_scan_repo=Depends(get_code_scan_repo),
    clock: Clock = Depends(get_clock),
) -> MatchAisleCodeScanDetectionsUseCase:
    return MatchAisleCodeScanDetectionsUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        code_scan_repo=code_scan_repo,
        clock=clock,
    )


def get_run_aisle_code_scan_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    code_scan_repo=Depends(get_code_scan_repo),
    scanner=Depends(get_code_scanner),
    content_reader=Depends(get_source_asset_content_reader),
    clock: Clock = Depends(get_clock),
    match_detections_use_case: MatchAisleCodeScanDetectionsUseCase = Depends(
        get_match_aisle_code_scan_detections_use_case
    ),
) -> RunAisleCodeScanUseCase:
    return RunAisleCodeScanUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        code_scan_repo=code_scan_repo,
        scanner=scanner,
        content_reader=content_reader,
        clock=clock,
        match_detections_use_case=match_detections_use_case,
    )


def get_list_aisle_code_scans_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    code_scan_repo=Depends(get_code_scan_repo),
) -> ListAisleCodeScansUseCase:
    return ListAisleCodeScansUseCase(
        aisle_repo=aisle_repo,
        code_scan_repo=code_scan_repo,
    )


def get_summarize_aisle_code_scans_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    code_scan_repo=Depends(get_code_scan_repo),
) -> SummarizeAisleCodeScansUseCase:
    return SummarizeAisleCodeScansUseCase(
        aisle_repo=aisle_repo,
        code_scan_repo=code_scan_repo,
    )


def get_get_position_code_scan_evidence_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    code_scan_repo=Depends(get_code_scan_repo),
) -> GetPositionCodeScanEvidenceUseCase:
    return GetPositionCodeScanEvidenceUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        code_scan_repo=code_scan_repo,
    )


def get_get_aisle_code_scan_review_signals_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    code_scan_repo=Depends(get_code_scan_repo),
) -> GetAisleCodeScanReviewSignalsUseCase:
    return GetAisleCodeScanReviewSignalsUseCase(
        aisle_repo=aisle_repo,
        code_scan_repo=code_scan_repo,
    )


def get_export_aisle_code_scans_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    code_scan_repo=Depends(get_code_scan_repo),
) -> ExportAisleCodeScansUseCase:
    return ExportAisleCodeScansUseCase(
        aisle_repo=aisle_repo,
        code_scan_repo=code_scan_repo,
    )


def get_upload_supplier_reference_images_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    reference_repo: SupplierReferenceImageRepository = Depends(
        get_supplier_reference_image_repo
    ),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
) -> UploadSupplierReferenceImagesUseCase:
    return UploadSupplierReferenceImagesUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
        clock=clock,
    )


def get_list_supplier_reference_images_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    reference_repo: SupplierReferenceImageRepository = Depends(
        get_supplier_reference_image_repo
    ),
) -> ListSupplierReferenceImagesUseCase:
    return ListSupplierReferenceImagesUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
    )


def get_get_supplier_reference_image_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    reference_repo: SupplierReferenceImageRepository = Depends(
        get_supplier_reference_image_repo
    ),
) -> GetSupplierReferenceImageUseCase:
    return GetSupplierReferenceImageUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
    )


def get_delete_supplier_reference_image_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    reference_repo: SupplierReferenceImageRepository = Depends(
        get_supplier_reference_image_repo
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> DeleteSupplierReferenceImageUseCase:
    return DeleteSupplierReferenceImageUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
    )


def get_list_supplier_prompt_configs_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
) -> ListSupplierPromptConfigsUseCase:
    from src.config import load_settings

    return ListSupplierPromptConfigsUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
        settings=load_settings(),
    )


def get_create_supplier_prompt_config_version_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
    clock: Clock = Depends(get_clock),
) -> CreateSupplierPromptConfigVersionUseCase:
    from src.config import load_settings

    return CreateSupplierPromptConfigVersionUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
        clock=clock,
        settings=load_settings(),
    )


def get_get_active_supplier_prompt_config_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
) -> GetActiveSupplierPromptConfigUseCase:
    from src.config import load_settings

    return GetActiveSupplierPromptConfigUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
        settings=load_settings(),
    )


def get_activate_supplier_prompt_config_version_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
) -> ActivateSupplierPromptConfigVersionUseCase:
    return ActivateSupplierPromptConfigVersionUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
    )


def get_get_supplier_prompt_config_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
) -> GetSupplierPromptConfigUseCase:
    return GetSupplierPromptConfigUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
    )


def get_list_supplier_extraction_profiles_use_case():
    return get_app_container().get_list_supplier_extraction_profiles_use_case()


def get_get_active_supplier_extraction_profile_use_case():
    return get_app_container().get_get_active_supplier_extraction_profile_use_case()


def get_get_supplier_extraction_profile_by_version_use_case():
    return get_app_container().get_get_supplier_extraction_profile_by_version_use_case()


def get_create_supplier_extraction_profile_version_use_case():
    return get_app_container().get_create_supplier_extraction_profile_version_use_case()


def get_activate_supplier_extraction_profile_version_use_case():
    return get_app_container().get_activate_supplier_extraction_profile_version_use_case()


def get_test_label_recognition_code_use_case():
    return get_app_container().get_test_label_recognition_code_use_case()


def get_clone_supplier_extraction_profile_use_case():
    return get_app_container().get_clone_supplier_extraction_profile_use_case()


def get_list_supplier_reference_annotations_use_case():
    return get_app_container().get_list_supplier_reference_annotations_use_case()


def get_replace_supplier_reference_annotations_use_case():
    return get_app_container().get_replace_supplier_reference_annotations_use_case()


def get_list_client_supplier_label_profiles_use_case():
    from src.application.use_cases.suppliers.manage_client_supplier_label_profiles import (
        ListClientSupplierLabelProfilesUseCase,
    )

    container = get_app_container()
    return ListClientSupplierLabelProfilesUseCase(
        client_supplier_repo=container.get_client_supplier_repo(),
        label_profile_repo=container.get_client_supplier_label_profile_repo(),
    )


def get_upsert_client_supplier_label_profile_use_case():
    from src.application.use_cases.suppliers.manage_client_supplier_label_profiles import (
        UpsertClientSupplierLabelProfileUseCase,
    )

    container = get_app_container()
    return UpsertClientSupplierLabelProfileUseCase(
        client_supplier_repo=container.get_client_supplier_repo(),
        label_profile_repo=container.get_client_supplier_label_profile_repo(),
        clock=container.get_clock(),
    )


def get_list_aisle_positions_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
) -> ListAislePositionsUseCase:
    from src.config import load_settings

    settings = load_settings()
    return ListAislePositionsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        result_context_resolver=result_context_resolver,
        product_record_repo=product_record_repo,
        positions_aisle_raw_cap=settings.v3_positions_aisle_raw_cap,
        reconciliation_repo=get_app_container().get_position_reconciliation_repo(),
        position_enrichment_enabled=settings.position_results_enrichment_enabled,
        override_repo=get_app_container().get_manual_position_override_repo(),
        label_repo=get_app_container().get_client_position_label_repo(),
    )


def get_list_review_queue_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
) -> ListReviewQueueUseCase:
    return ListReviewQueueUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
    )


def get_get_position_detail_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    evidence_repo: EvidenceRepository = Depends(get_evidence_repo),
    review_repo: ReviewActionRepository = Depends(get_review_action_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
) -> GetPositionDetailUseCase:
    from src.config import load_settings

    return GetPositionDetailUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        evidence_repo=evidence_repo,
        review_repo=review_repo,
        job_repo=job_repo,
        result_context_resolver=result_context_resolver,
        positions_aisle_raw_cap=load_settings().v3_positions_aisle_raw_cap,
    )


def get_confirm_position_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    review_repo: ReviewActionRepository = Depends(get_review_action_repo),
    clock: Clock = Depends(get_clock),
    aisle_review_sync: AisleReviewLifecycleSync = Depends(get_aisle_review_lifecycle_sync),
) -> ConfirmPositionUseCase:
    return ConfirmPositionUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=aisle_review_sync,
    )


def get_update_product_quantity_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    review_repo: ReviewActionRepository = Depends(get_review_action_repo),
    clock: Clock = Depends(get_clock),
    aisle_review_sync: AisleReviewLifecycleSync = Depends(get_aisle_review_lifecycle_sync),
) -> UpdateProductQuantityUseCase:
    return UpdateProductQuantityUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=aisle_review_sync,
    )


def get_update_product_sku_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    review_repo: ReviewActionRepository = Depends(get_review_action_repo),
    clock: Clock = Depends(get_clock),
    aisle_review_sync: AisleReviewLifecycleSync = Depends(get_aisle_review_lifecycle_sync),
) -> UpdateProductSkuUseCase:
    return UpdateProductSkuUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=aisle_review_sync,
    )


def get_update_position_code_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    review_repo: ReviewActionRepository = Depends(get_review_action_repo),
    clock: Clock = Depends(get_clock),
    aisle_review_sync: AisleReviewLifecycleSync = Depends(get_aisle_review_lifecycle_sync),
) -> UpdatePositionCodeUseCase:
    return UpdatePositionCodeUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=aisle_review_sync,
    )


def get_mark_position_unknown_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    review_repo: ReviewActionRepository = Depends(get_review_action_repo),
    clock: Clock = Depends(get_clock),
    aisle_review_sync: AisleReviewLifecycleSync = Depends(get_aisle_review_lifecycle_sync),
) -> MarkPositionUnknownUseCase:
    return MarkPositionUnknownUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=aisle_review_sync,
    )


def get_mark_position_image_mismatch_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    review_repo: ReviewActionRepository = Depends(get_review_action_repo),
    clock: Clock = Depends(get_clock),
    aisle_review_sync: AisleReviewLifecycleSync = Depends(get_aisle_review_lifecycle_sync),
) -> MarkPositionImageMismatchUseCase:
    return MarkPositionImageMismatchUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=aisle_review_sync,
    )


def get_delete_position_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    review_repo: ReviewActionRepository = Depends(get_review_action_repo),
    clock: Clock = Depends(get_clock),
    aisle_review_sync: AisleReviewLifecycleSync = Depends(get_aisle_review_lifecycle_sync),
) -> DeletePositionUseCase:
    return DeletePositionUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=aisle_review_sync,
    )


def get_preview_merge_positions_use_case(
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
):
    from src.application.use_cases.positions.merge_positions import PreviewMergePositionsUseCase

    return PreviewMergePositionsUseCase(
        access_policy=access_policy,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
    )


def get_confirm_merge_positions_use_case(
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    review_repo: ReviewActionRepository = Depends(get_review_action_repo),
    clock: Clock = Depends(get_clock),
    aisle_review_sync: AisleReviewLifecycleSync = Depends(get_aisle_review_lifecycle_sync),
):
    from src.application.use_cases.positions.merge_positions import ConfirmMergePositionsUseCase

    return ConfirmMergePositionsUseCase(
        access_policy=access_policy,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=aisle_review_sync,
        uow_factory=get_app_container().get_position_merge_uow_factory(),
    )


def get_run_aisle_merge_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    recompute_uc=Depends(get_recompute_consolidated_counts_use_case),
) -> RunAisleMergeUseCase:
    return RunAisleMergeUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        recompute_use_case=recompute_uc,
    )


def get_get_aisle_merge_results_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    final_count_repo=Depends(get_final_count_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
) -> GetAisleMergeResultsUseCase:
    return GetAisleMergeResultsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        final_count_repo=final_count_repo,
        result_context_resolver=result_context_resolver,
    )


def get_list_aisle_jobs_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> ListAisleJobsUseCase:
    return ListAisleJobsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
    )


def get_resolve_aisle_job_for_inventory_read_use_case(
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
) -> ResolveAisleJobForInventoryReadUseCase:
    return ResolveAisleJobForInventoryReadUseCase(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
    )


def get_observability_inventory_guard(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
):
    """Company-scope check without injecting ``Depends(get_*_repo)`` into route signatures."""
    from src.application.services.observability_access import (
        ObservabilityAccessContext,
        assert_inventory_client_scope,
    )
    from src.domain.inventory.entities import Inventory

    def _guard(inventory_id: str, user: AuthUser) -> Inventory:
        return assert_inventory_client_scope(
            inventory_repo,
            inventory_id=inventory_id,
            access=ObservabilityAccessContext.from_user(user),
        )

    return _guard


def get_job_source_asset_repo():
    return get_app_container().get_job_source_asset_repo()


def get_manual_image_coverage_repo():
    return get_app_container().get_manual_image_coverage_repo()


def get_job_image_coverage_repo():
    return get_app_container().get_job_image_coverage_repo()


def get_manual_image_result_uow_factory():
    return get_app_container().get_manual_image_result_uow_factory()


def get_list_job_image_results_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    job_source_asset_repo=Depends(get_job_source_asset_repo),
    coverage_repo=Depends(get_job_image_coverage_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
):
    from src.application.use_cases.positions.list_job_image_results import (
        ListJobImageResultsUseCase,
    )

    return ListJobImageResultsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_source_asset_repo=job_source_asset_repo,
        coverage_repo=coverage_repo,
        product_record_repo=product_record_repo,
        detection_repo=get_app_container().get_image_position_label_detection_repo(),
    )


def get_processing_event_repo():
    return get_app_container().get_processing_event_repo()


def _build_processing_scope_validator(c):
    from src.application.services.image_processing.processing_asset_scope_validator import (
        ProcessingAssetScopeValidator,
    )

    return ProcessingAssetScopeValidator(
        inventory_repo=c.get_inventory_repo(),
        aisle_repo=c.get_aisle_repo(),
        job_repo=c.get_job_repo(),
        job_source_asset_repo=c.get_job_source_asset_repo(),
    )


def _build_processing_idempotency_service(c):
    from src.application.services.image_processing.processing_action_idempotency_service import (
        ProcessingActionIdempotencyService,
    )

    return ProcessingActionIdempotencyService(c.get_processing_action_idempotency_repo())


def get_processing_action_idempotency_service():
    return _build_processing_idempotency_service(get_app_container())


def _build_processing_event_publisher(c):
    from src.application.services.image_processing.processing_event_publisher import (
        RepositoryProcessingEventPublisher,
    )

    return RepositoryProcessingEventPublisher(
        event_repo=c.get_processing_event_repo(),
        clock=c.get_clock(),
    )


def _build_queue_asset_command_use_case(c):
    from src.application.use_cases.processing.reprocess_asset import (
        QueueAssetProcessingCommandUseCase,
    )

    return QueueAssetProcessingCommandUseCase(
        scope_validator=_build_processing_scope_validator(c),
        state_repo=c.get_job_asset_processing_state_repo(),
        command_repo=c.get_asset_processing_command_repo(),
        idempotency=_build_processing_idempotency_service(c),
        clock=c.get_clock(),
        event_publisher=_build_processing_event_publisher(c),
    )


def get_list_asset_processing_use_case():
    from src.application.use_cases.processing.asset_processing_queries import (
        ListAssetProcessingUseCase,
    )

    c = get_app_container()
    return ListAssetProcessingUseCase(
        inventory_repo=c.get_inventory_repo(),
        aisle_repo=c.get_aisle_repo(),
        job_repo=c.get_job_repo(),
        state_repo=c.get_job_asset_processing_state_repo(),
        attempt_repo=c.get_processing_attempt_repo(),
        job_source_asset_repo=c.get_job_source_asset_repo(),
        source_asset_repo=c.get_source_asset_repo(),
        external_request_repo=c.get_external_image_analysis_request_repo(),
        coverage_repo=c.get_manual_image_coverage_repo(),
    )


def get_get_asset_processing_detail_use_case():
    from src.application.use_cases.processing.asset_processing_queries import (
        GetAssetProcessingDetailUseCase,
    )

    c = get_app_container()
    return GetAssetProcessingDetailUseCase(
        inventory_repo=c.get_inventory_repo(),
        aisle_repo=c.get_aisle_repo(),
        job_repo=c.get_job_repo(),
        state_repo=c.get_job_asset_processing_state_repo(),
        attempt_repo=c.get_processing_attempt_repo(),
        job_source_asset_repo=c.get_job_source_asset_repo(),
        source_asset_repo=c.get_source_asset_repo(),
        external_request_repo=c.get_external_image_analysis_request_repo(),
        coverage_repo=c.get_manual_image_coverage_repo(),
        event_repo=c.get_processing_event_repo(),
        position_repo=c.get_position_repo(),
    )


def get_list_processing_events_use_case():
    from src.application.use_cases.processing.list_processing_events import (
        ListProcessingEventsUseCase,
    )

    c = get_app_container()
    return ListProcessingEventsUseCase(
        inventory_repo=c.get_inventory_repo(),
        aisle_repo=c.get_aisle_repo(),
        job_repo=c.get_job_repo(),
        job_source_asset_repo=c.get_job_source_asset_repo(),
        event_repo=c.get_processing_event_repo(),
    )


def get_reprocess_asset_use_case():
    from src.application.use_cases.processing.reprocess_asset import ReprocessAssetUseCase

    c = get_app_container()
    return ReprocessAssetUseCase(_build_queue_asset_command_use_case(c))


def get_retry_asset_persistence_use_case():
    from src.application.use_cases.processing.reprocess_asset import (
        RetryAssetPersistenceUseCase,
    )

    c = get_app_container()
    return RetryAssetPersistenceUseCase(_build_queue_asset_command_use_case(c))


def get_send_asset_to_external_use_case():
    from src.application.use_cases.processing.reprocess_asset import (
        SendAssetToExternalUseCase,
    )

    c = get_app_container()
    return SendAssetToExternalUseCase(_build_queue_asset_command_use_case(c))


def get_invalidate_asset_result_use_case():
    from src.application.use_cases.processing.invalidate_asset_result import (
        InvalidateAssetResultUseCase,
    )

    c = get_app_container()
    return InvalidateAssetResultUseCase(
        scope_validator=_build_processing_scope_validator(c),
        state_repo=c.get_job_asset_processing_state_repo(),
        coverage_repo=c.get_manual_image_coverage_repo(),
        position_repo=c.get_position_repo(),
        idempotency=_build_processing_idempotency_service(c),
        clock=c.get_clock(),
        event_publisher=_build_processing_event_publisher(c),
    )


def get_single_asset_command_executor():
    from src.application.services.image_processing.single_asset_command_executor import (
        SingleAssetCommandExecutor,
    )

    c = get_app_container()
    return SingleAssetCommandExecutor(
        command_repo=c.get_asset_processing_command_repo(),
        state_repo=c.get_job_asset_processing_state_repo(),
        job_repo=c.get_job_repo(),
        source_asset_repo=c.get_source_asset_repo(),
        clock=c.get_clock(),
        external_request_repo=c.get_external_image_analysis_request_repo(),
        event_publisher=_build_processing_event_publisher(c),
    )


def get_create_manual_image_result_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    job_source_asset_repo=Depends(get_job_source_asset_repo),
    source_asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    clock: Clock = Depends(get_clock),
    unit_of_work_factory=Depends(get_manual_image_result_uow_factory),
):
    from src.application.use_cases.positions.create_manual_image_result import (
        CreateManualImageResultUseCase,
    )

    return CreateManualImageResultUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_source_asset_repo=job_source_asset_repo,
        source_asset_repo=source_asset_repo,
        clock=clock,
        unit_of_work_factory=unit_of_work_factory,
    )


def get_job_artifact_catalog_service(
    manifest_store=Depends(get_artifact_manifest_store),
    job_source_asset_repo=Depends(get_job_source_asset_repo),
):
    from src.application.services.job_artifact_catalog_service import JobArtifactCatalogService

    return JobArtifactCatalogService(
        manifest_store=manifest_store,
        job_source_asset_repo=job_source_asset_repo,
    )


def get_job_retry_chain_service(
    job_repo: JobRepository = Depends(get_job_repo),
):
    from src.application.services.job_retry_chain_service import JobRetryChainService

    return JobRetryChainService(job_repo=job_repo)


def get_run_auditability_service(
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    artifact_storage=Depends(get_artifact_storage),
):
    """Read-only job auditability aggregation (Phase H2)."""
    from src.application.services.run_auditability_service import RunAuditabilityService
    from src.infrastructure.artifacts.run_audit_execution_log_loader import (
        DefaultRunAuditExecutionLogLoader,
    )
    from src.infrastructure.artifacts.stored_artifact_reader import DefaultStoredArtifactReader

    return RunAuditabilityService(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
        stored_artifact_reader=DefaultStoredArtifactReader(job_repo, artifact_storage),
        execution_log_loader=DefaultRunAuditExecutionLogLoader(artifact_storage),
    )


def get_observability_metrics_service(
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
):
    """Read-only observability metrics (Phase H5)."""
    from src.application.services.observability_metrics_service import ObservabilityMetricsService

    return ObservabilityMetricsService(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
    )


def get_compare_aisle_runs_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
) -> CompareAisleRunsUseCase:
    from src.config import load_settings

    return CompareAisleRunsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        positions_aisle_raw_cap=load_settings().v3_positions_aisle_raw_cap,
    )


def get_compare_many_aisle_runs_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
) -> CompareManyAisleRunsUseCase:
    from src.config import load_settings

    return CompareManyAisleRunsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        positions_aisle_raw_cap=load_settings().v3_positions_aisle_raw_cap,
    )


def get_promote_aisle_operational_job_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> PromoteAisleOperationalJobUseCase:
    from src.runtime.v3_deps import get_app_container

    return PromoteAisleOperationalJobUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        operational_promotion_service=get_app_container().build_operational_result_promotion_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
        ),
    )


def get_export_aisle_benchmark_run_csv_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
) -> ExportAisleBenchmarkRunCsvUseCase:
    from src.config import load_settings

    return ExportAisleBenchmarkRunCsvUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        positions_aisle_raw_cap=load_settings().v3_positions_aisle_raw_cap,
    )


def get_export_aisle_benchmark_compare_csv_use_case(
    compare_uc: CompareAisleRunsUseCase = Depends(get_compare_aisle_runs_use_case),
) -> ExportAisleBenchmarkCompareCsvUseCase:
    return ExportAisleBenchmarkCompareCsvUseCase(compare_uc=compare_uc)


def get_analytics_query_service(
    repo=Depends(get_analytics_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
) -> AnalyticsQueryService:
    return AnalyticsQueryService(repo, aisle_repo)


def get_analytics_cost_summary_service(
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
):
    from src.application.services.analytics_cost_counted_quantity import (
        AnalyticsCostCountedQuantityService,
    )
    from src.application.services.analytics_cost_summary_service import AnalyticsCostSummaryService

    return AnalyticsCostSummaryService(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
        counted_quantity_service=AnalyticsCostCountedQuantityService(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            job_repo=job_repo,
            result_context_resolver=result_context_resolver,
        ),
    )


def get_create_capture_session_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.create_capture_session import (
        CreateCaptureSessionUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return CreateCaptureSessionUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=s.v3_capture_max_open_sessions_per_aisle,
    )


def get_close_capture_session_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.close_capture_session import (
        CloseCaptureSessionUseCase,
    )

    return CloseCaptureSessionUseCase(session_repo=session_repo, item_repo=item_repo, clock=clock)


def get_cancel_capture_session_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.cancel_capture_session import (
        CancelCaptureSessionUseCase,
    )

    return CancelCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=artifact_storage,
        clock=clock,
    )


def get_list_capture_sessions_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
):
    from src.application.use_cases.capture_sessions.list_capture_sessions import (
        ListCaptureSessionsUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return ListCaptureSessionsUseCase(
        inventory_repo=inventory_repo,
        session_repo=session_repo,
        default_page_size=s.v3_capture_session_list_default_page_size,
        max_page_size=s.v3_capture_session_list_max_page_size,
    )


def get_get_capture_session_detail_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
):
    from src.application.use_cases.capture_sessions.get_capture_session_detail import (
        GetCaptureSessionDetailUseCase,
    )

    return GetCaptureSessionDetailUseCase(
        inventory_repo=inventory_repo,
        session_repo=session_repo,
        item_repo=item_repo,
    )


def get_capture_staging_time_metadata_extractor():
    from src.application.services.capture_staging_time_metadata import (
        PillowCaptureStagingTimeMetadataExtractor,
    )
    from src.config import load_settings

    s = load_settings()
    return PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=s.v3_capture_time_confidence_exif,
        confidence_mtime=s.v3_capture_time_confidence_mtime,
        confidence_fallback=s.v3_capture_time_confidence_fallback,
    )


def get_upload_capture_session_staging_items_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
    time_metadata_extractor=Depends(get_capture_staging_time_metadata_extractor),
    access_policy: InventoryAccessPolicy = Depends(get_capture_session_access_policy),
):
    from src.application.services.upload_request_limits import UploadRequestLimitPolicy
    from src.application.use_cases.capture_sessions.upload_capture_session_staging_items import (
        UploadCaptureSessionStagingItemsUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    policy = UploadRequestLimitPolicy.from_settings(s)
    return UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=artifact_storage,
        clock=clock,
        staging_prefix=s.v3_capture_staging_storage_prefix,
        max_upload_bytes=policy.max_file_size_bytes,
        time_metadata_extractor=time_metadata_extractor,
        access_policy=access_policy,
        upload_policy=policy,
    )


def get_update_capture_session_clock_offset_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.update_capture_session_clock_offset import (
        UpdateCaptureSessionClockOffsetUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return UpdateCaptureSessionClockOffsetUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        clock=clock,
        min_offset_seconds=s.v3_capture_clock_offset_min_seconds,
        max_offset_seconds=s.v3_capture_clock_offset_max_seconds,
    )


def get_compute_capture_session_assignment_preview_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.compute_capture_session_assignment_preview import (
        ComputeCaptureSessionAssignmentPreviewUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return ComputeCaptureSessionAssignmentPreviewUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        position_repo=position_repo,
        clock=clock,
        preview_max_positions=s.v3_capture_preview_max_positions,
    )


def get_compute_capture_session_groups_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.compute_capture_session_groups import (
        ComputeCaptureSessionGroupsUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return ComputeCaptureSessionGroupsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        group_repo=group_repo,
        clock=clock,
        max_time_gap_seconds=s.v3_capture_grouping_max_gap_seconds,
    )


def get_get_capture_session_groups_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
):
    from src.application.use_cases.capture_sessions.get_capture_session_groups import (
        GetCaptureSessionGroupsUseCase,
    )

    return GetCaptureSessionGroupsUseCase(session_repo=session_repo, group_repo=group_repo)


def get_assign_capture_session_group_to_existing_aisle_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.assign_capture_session_group_to_existing_aisle import (
        AssignCaptureSessionGroupToExistingAisleUseCase,
    )

    return AssignCaptureSessionGroupToExistingAisleUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        aisle_repo=aisle_repo,
        clock=clock,
    )


def get_create_aisle_and_assign_capture_session_group_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    create_aisle: CreateAisleUseCase = Depends(get_create_aisle_use_case),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.create_aisle_and_assign_capture_session_group import (
        CreateAisleAndAssignCaptureSessionGroupUseCase,
    )

    return CreateAisleAndAssignCaptureSessionGroupUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        create_aisle=create_aisle,
        clock=clock,
    )


def get_compute_materialized_capture_session_group_preview_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
):
    from src.application.use_cases.capture_sessions.compute_materialized_capture_session_group_preview import (
        ComputeMaterializedCaptureSessionGroupPreviewUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return ComputeMaterializedCaptureSessionGroupPreviewUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        item_repo=item_repo,
        position_repo=position_repo,
        asset_repo=asset_repo,
        preview_max_positions=s.v3_capture_preview_max_positions,
    )


def get_materialize_capture_session_group_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    artifact_storage=Depends(get_artifact_storage),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.materialize_capture_session_group import (
        MaterializeCaptureSessionGroupUseCase,
    )

    return MaterializeCaptureSessionGroupUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        item_repo=item_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=artifact_storage,
        status_reconciler=status_reconciler,
        clock=clock,
    )


def get_materialize_capture_session_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    confirm_repo: CaptureSessionConfirmIdempotencyRepository = Depends(
        get_capture_session_confirm_repo
    ),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    artifact_storage=Depends(get_artifact_storage),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.materialize_capture_session import (
        MaterializeCaptureSessionUseCase,
    )

    return MaterializeCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        confirm_repo=confirm_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=artifact_storage,
        status_reconciler=status_reconciler,
        clock=clock,
    )


def get_create_ordered_capture_session_use_case(
    session_repo=Depends(get_ordered_capture_session_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.ordered_capture.manage_ordered_capture_session import (
        CreateOrderedCaptureSessionUseCase,
    )

    return CreateOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        access_policy=access_policy,
        clock=clock,
    )


def get_get_ordered_capture_session_use_case(
    session_repo=Depends(get_ordered_capture_session_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.ordered_capture.manage_ordered_capture_session import (
        GetOrderedCaptureSessionUseCase,
    )

    return GetOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        access_policy=access_policy,
    )


def get_seal_ordered_capture_session_use_case(
    session_repo=Depends(get_ordered_capture_session_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.ordered_capture.manage_ordered_capture_session import (
        SealOrderedCaptureSessionUseCase,
    )

    return SealOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        asset_repo=asset_repo,
        access_policy=access_policy,
        clock=clock,
    )


def get_create_aisle_location_use_case(
    location_repo=Depends(get_aisle_location_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        CreateAisleLocationUseCase,
    )

    return CreateAisleLocationUseCase(
        location_repo=location_repo,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        access_policy=access_policy,
        clock=clock,
    )


def get_list_aisle_locations_use_case(
    location_repo=Depends(get_aisle_location_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        ListAisleLocationsUseCase,
    )

    return ListAisleLocationsUseCase(
        location_repo=location_repo,
        access_policy=access_policy,
    )


def get_get_aisle_location_use_case(
    location_repo=Depends(get_aisle_location_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        GetAisleLocationUseCase,
    )

    return GetAisleLocationUseCase(
        location_repo=location_repo,
        access_policy=access_policy,
    )


def get_update_aisle_location_use_case(
    location_repo=Depends(get_aisle_location_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        UpdateAisleLocationUseCase,
    )

    return UpdateAisleLocationUseCase(
        location_repo=location_repo,
        access_policy=access_policy,
        clock=clock,
    )


def get_issue_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        IssueAisleLocationLabelUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=settings.positioning_label_hmac_secret or None,
            key_version=int(settings.positioning_label_hmac_key_version),
            previous_secrets=parse_previous_secrets(
                settings.positioning_label_hmac_previous_secrets
            ),
            required=bool(settings.positioning_label_signing_required),
        )
    )
    return IssueAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        access_policy=access_policy,
        clock=clock,
        signing=signing,
    )


def get_aisle_location_label_artifact_repo():
    return get_app_container().get_aisle_location_label_artifact_repo()


def get_image_position_label_detection_repo():
    return get_app_container().get_image_position_label_detection_repo()


def get_position_reconciliation_repo():
    return get_app_container().get_position_reconciliation_repo()


def get_client_position_label_repo():
    return get_app_container().get_client_position_label_repo()


def get_manual_position_override_repo():
    return get_app_container().get_manual_position_override_repo()


def get_position_override_scope_resolver(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_repo: ProductRecordRepository = Depends(get_product_record_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.services.position_overrides.position_override_scope import (
        PositionOverrideScopeResolver,
    )

    return PositionOverrideScopeResolver(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        product_repo=product_repo,
        access_policy=access_policy,
    )


def get_effective_position_reader(
    label_repo=Depends(get_client_position_label_repo),
    override_repo=Depends(get_manual_position_override_repo),
    reconciliation_repo=Depends(get_position_reconciliation_repo),
):
    from src.application.services.position_overrides.effective_position_reader import (
        EffectivePositionReader,
    )
    from src.application.services.position_reconciliation.published_assignment_reader import (
        PublishedPositionAssignmentReader,
    )
    from src.config import load_settings

    settings = load_settings()
    automatic_reader = PublishedPositionAssignmentReader(
        reconciliation_repo=reconciliation_repo,
        enrichment_enabled=settings.position_results_enrichment_enabled,
    )
    effective_reader = EffectivePositionReader(
        automatic_reader=automatic_reader,
        override_repo=override_repo,
        label_repo=label_repo,
    )
    return effective_reader


def get_manage_position_override_use_case(
    label_repo=Depends(get_client_position_label_repo),
    override_repo=Depends(get_manual_position_override_repo),
    effective_reader=Depends(get_effective_position_reader),
    scope_resolver=Depends(get_position_override_scope_resolver),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.position_overrides.manage import (
        ManagePositionOverrideUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    return ManagePositionOverrideUseCase(
        label_repo=label_repo,
        override_repo=override_repo,
        effective_reader=effective_reader,
        scope_resolver=scope_resolver,
        writes_enabled=settings.position_manual_overrides_enabled,
        clock=clock,
    )


def get_list_position_override_history_use_case(
    override_repo=Depends(get_manual_position_override_repo),
    reconciliation_repo=Depends(get_position_reconciliation_repo),
    scope_resolver=Depends(get_position_override_scope_resolver),
    effective_reader=Depends(get_effective_position_reader),
):
    from src.application.use_cases.position_overrides.manage import (
        ListPositionOverrideHistoryUseCase,
    )

    return ListPositionOverrideHistoryUseCase(
        override_repo=override_repo,
        reconciliation_repo=reconciliation_repo,
        scope_resolver=scope_resolver,
        effective_reader=effective_reader,
    )


def get_reconcile_job_positions_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    source_asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    job_source_asset_repo=Depends(get_job_source_asset_repo),
    coverage_repo=Depends(get_job_image_coverage_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    detection_repo=Depends(get_image_position_label_detection_repo),
    reconciliation_repo=Depends(get_position_reconciliation_repo),
    ordered_session_repo=Depends(get_ordered_capture_session_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.services.position_reconciliation.readiness import (
        PositionReconciliationReadinessPolicy,
    )
    from src.application.use_cases.position_reconciliation.reconcile_job_positions import (
        ReconcileJobPositionsUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    return ReconcileJobPositionsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        source_asset_repo=source_asset_repo,
        job_source_asset_repo=job_source_asset_repo,
        coverage_repo=coverage_repo,
        product_record_repo=product_record_repo,
        detection_repo=detection_repo,
        reconciliation_repo=reconciliation_repo,
        clock=clock,
        position_repo=position_repo,
        readiness_policy=PositionReconciliationReadinessPolicy(ordered_session_repo),
        access_policy=access_policy,
        enabled=settings.position_reconciliation_enabled,
        persistence_enabled=settings.position_reconciliation_persistence_enabled,
    )


def get_aisle_operational_positioning_view_use_case(
    status_use_case: GetAisleProcessingStatusUseCase = Depends(
        get_get_aisle_processing_status_use_case
    ),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    reconciliation_repo=Depends(get_position_reconciliation_repo),
    detection_repo=Depends(get_image_position_label_detection_repo),
    override_repo=Depends(get_manual_position_override_repo),
    label_repo=Depends(get_client_position_label_repo),
    job_source_asset_repo=Depends(get_job_source_asset_repo),
    coverage_repo=Depends(get_job_image_coverage_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.positioning_operational.get_aisle_operational_view import (
        GetAisleOperationalPositioningViewUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    return GetAisleOperationalPositioningViewUseCase(
        status_use_case=status_use_case,
        inventory_repo=inventory_repo,
        access_policy=access_policy,
        reconciliation_repo=reconciliation_repo,
        detection_repo=detection_repo,
        override_repo=override_repo,
        label_repo=label_repo,
        job_source_asset_repo=job_source_asset_repo,
        coverage_repo=coverage_repo,
        product_record_repo=product_record_repo,
        clock=clock,
        operational_ux_enabled=settings.position_operational_ux_enabled,
        reprocessing_enabled=settings.position_reprocessing_enabled,
        recovery_enabled=settings.position_processing_recovery_enabled,
        overrides_enabled=settings.position_manual_overrides_enabled,
        enrichment_enabled=settings.position_results_enrichment_enabled,
        local_csv_result_writer=container.get_local_csv_result_writer(),
    )


def get_aisle_positioning_sequence_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    reconciliation_repo=Depends(get_position_reconciliation_repo),
    detection_repo=Depends(get_image_position_label_detection_repo),
    job_source_asset_repo=Depends(get_job_source_asset_repo),
    override_repo=Depends(get_manual_position_override_repo),
    label_repo=Depends(get_client_position_label_repo),
    coverage_repo=Depends(get_job_image_coverage_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
):
    from src.application.use_cases.positioning_operational.get_aisle_positioning_sequence import (
        GetAislePositioningSequenceUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    return GetAislePositioningSequenceUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        access_policy=access_policy,
        reconciliation_repo=reconciliation_repo,
        detection_repo=detection_repo,
        job_source_asset_repo=job_source_asset_repo,
        override_repo=override_repo,
        label_repo=label_repo,
        coverage_repo=coverage_repo,
        product_record_repo=product_record_repo,
        enrichment_enabled=settings.position_results_enrichment_enabled,
    )


def get_reprocess_aisle_positioning_use_case(
    status_use_case: GetAisleProcessingStatusUseCase = Depends(
        get_get_aisle_processing_status_use_case
    ),
    start_processing=Depends(get_start_aisle_processing_use_case),
    reconcile=Depends(get_reconcile_job_positions_use_case),
    clock: Clock = Depends(get_clock),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    idempotency=Depends(get_processing_action_idempotency_service),
    override_repo=Depends(get_manual_position_override_repo),
    reconciliation_repo=Depends(get_position_reconciliation_repo),
):
    from src.application.use_cases.positioning_operational.reprocess_aisle_positioning import (
        ReprocessAislePositioningUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    return ReprocessAislePositioningUseCase(
        status_use_case=status_use_case,
        start_processing=start_processing,
        reconcile=reconcile,
        clock=clock,
        access_policy=access_policy,
        idempotency=idempotency,
        override_repo=override_repo,
        reconciliation_repo=reconciliation_repo,
        reprocessing_enabled=settings.position_reprocessing_enabled,
    )


def get_render_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    artifact_repo=Depends(get_aisle_location_label_artifact_repo),
    inventory_repo=Depends(get_inventory_repo),
    aisle_repo=Depends(get_aisle_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.services.positioning_label_renderer import PositioningLabelRenderer
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        RenderAisleLocationLabelUseCase,
    )

    container = get_app_container()
    return RenderAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        artifact_repo=artifact_repo,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        artifact_store=container.get_artifact_store(),
        renderer=PositioningLabelRenderer(),
        access_policy=access_policy,
        clock=clock,
    )


def get_download_aisle_location_label_use_case(
    render_uc=Depends(get_render_aisle_location_label_use_case),
    label_repo=Depends(get_aisle_location_label_repo),
):
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        DownloadAisleLocationLabelUseCase,
    )

    return DownloadAisleLocationLabelUseCase(
        render_use_case=render_uc,
        label_repo=label_repo,
        artifact_store=get_app_container().get_artifact_store(),
    )


def get_get_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        GetAisleLocationLabelUseCase,
    )

    return GetAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        access_policy=access_policy,
    )


def get_replace_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.ports.aisle_location_repository import (
        AisleLocationLabelReplaceUnitOfWork,
    )
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        ReplaceAisleLocationLabelUseCase,
    )
    from src.config import load_settings
    from src.infrastructure.persistence.sql_aisle_location_label_replace_uow import (
        MemoryAisleLocationLabelReplaceUnitOfWork,
        SqlAisleLocationLabelReplaceUnitOfWork,
    )
    from src.infrastructure.repositories.memory_aisle_location_repository import (
        MemoryAisleLocationLabelRepository,
    )

    settings = load_settings()
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=settings.positioning_label_hmac_secret or None,
            key_version=int(settings.positioning_label_hmac_key_version),
            previous_secrets=parse_previous_secrets(
                settings.positioning_label_hmac_previous_secrets
            ),
            required=bool(settings.positioning_label_signing_required),
        )
    )
    container = get_app_container()
    replace_uow: AisleLocationLabelReplaceUnitOfWork
    if container.is_sql_repository_backend():
        replace_uow = SqlAisleLocationLabelReplaceUnitOfWork(container._get_v3_sql_client())
    else:
        if not isinstance(label_repo, MemoryAisleLocationLabelRepository):
            raise RuntimeError(
                "Memory replace UoW requires MemoryAisleLocationLabelRepository"
            )
        replace_uow = MemoryAisleLocationLabelReplaceUnitOfWork(label_repo)
    return ReplaceAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        replace_uow=replace_uow,
        access_policy=access_policy,
        clock=clock,
        signing=signing,
    )


def get_batch_render_aisle_location_labels_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    issue_uc=Depends(get_issue_aisle_location_label_use_case),
    inventory_repo=Depends(get_inventory_repo),
    aisle_repo=Depends(get_aisle_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.services.positioning_label_renderer import PositioningLabelRenderer
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        BatchRenderAisleLocationLabelsUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    max_batch = min(
        int(settings.position_label_max_batch_size),
        int(settings.position_label_batch_sync_limit),
    )
    return BatchRenderAisleLocationLabelsUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        issue_use_case=issue_uc,
        access_policy=access_policy,
        renderer=PositioningLabelRenderer(),
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        artifact_store=get_app_container().get_artifact_store(),
        clock=clock,
        max_batch_size=max_batch,
        max_pdf_bytes=int(settings.position_label_max_pdf_bytes),
    )


def get_list_aisle_location_labels_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        ListAisleLocationLabelsUseCase,
    )

    return ListAisleLocationLabelsUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        access_policy=access_policy,
    )


def get_invalidate_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        InvalidateAisleLocationLabelUseCase,
    )

    return InvalidateAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        access_policy=access_policy,
        clock=clock,
    )
