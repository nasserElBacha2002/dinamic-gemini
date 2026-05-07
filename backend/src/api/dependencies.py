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

from fastapi import Depends

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
    InventoryVisualReferenceRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
    SourceAssetRepository,
)
from src.application.ports.services import MetricsCalculator, WorkerLaunchService
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.analytics_query_service import AnalyticsQueryService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.operational_execution_config_resolver import (
    OperationalExecutionConfigResolver,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.cancel_aisle_job import CancelAisleJobUseCase
from src.application.use_cases.compare_aisle_runs import CompareAisleRunsUseCase
from src.application.use_cases.compare_many_aisle_runs import CompareManyAisleRunsUseCase
from src.application.use_cases.confirm_position import ConfirmPositionUseCase
from src.application.use_cases.create_aisle import CreateAisleUseCase
from src.application.use_cases.create_client import CreateClientUseCase
from src.application.use_cases.create_client_supplier import CreateClientSupplierUseCase
from src.application.use_cases.create_inventory import CreateInventoryUseCase
from src.application.use_cases.delete_aisle_source_asset import DeleteAisleSourceAssetUseCase
from src.application.use_cases.delete_position import DeletePositionUseCase
from src.application.use_cases.export_aisle_benchmark import (
    ExportAisleBenchmarkCompareCsvUseCase,
    ExportAisleBenchmarkRunCsvUseCase,
)
from src.application.use_cases.export_inventory_results import (
    ExportAisleResultsCsvUseCase,
    ExportInventoryResultsUseCase,
)
from src.application.use_cases.get_aisle_merge_results import (
    GetAisleMergeResultsUseCase,
)
from src.application.use_cases.get_aisle_processing_status import GetAisleProcessingStatusUseCase
from src.application.use_cases.get_client import GetClientUseCase
from src.application.use_cases.get_client_supplier import GetClientSupplierUseCase
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.get_inventory_metrics import GetInventoryMetricsUseCase
from src.application.use_cases.get_position_detail import GetPositionDetailUseCase
from src.application.use_cases.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.list_aisle_jobs import ListAisleJobsUseCase
from src.application.use_cases.list_aisle_positions import ListAislePositionsUseCase
from src.application.use_cases.list_aisles_by_inventory import ListAislesByInventoryUseCase
from src.application.use_cases.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.list_client_suppliers import ListClientSuppliersUseCase
from src.application.use_cases.list_clients import ListClientsUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase
from src.application.use_cases.list_inventory_list_items import ListInventoryListItemsUseCase
from src.application.use_cases.list_review_queue import ListReviewQueueUseCase
from src.application.use_cases.manage_inventory_visual_references import (
    DeleteInventoryVisualReferenceUseCase,
    ReplaceInventoryVisualReferenceUseCase,
)
from src.application.use_cases.mark_position_image_mismatch import MarkPositionImageMismatchUseCase
from src.application.use_cases.mark_position_unknown import MarkPositionUnknownUseCase
from src.application.use_cases.promote_aisle_operational_job import (
    PromoteAisleOperationalJobUseCase,
)
from src.application.use_cases.resolve_aisle_job_for_inventory_read import (
    ResolveAisleJobForInventoryReadUseCase,
)
from src.application.use_cases.retry_aisle_job import RetryAisleJobUseCase
from src.application.use_cases.run_aisle_merge import RunAisleMergeUseCase
from src.application.use_cases.start_aisle_processing import StartAisleProcessingUseCase
from src.application.use_cases.update_position_code import UpdatePositionCodeUseCase
from src.application.use_cases.update_product_quantity import UpdateProductQuantityUseCase
from src.application.use_cases.update_product_sku import UpdateProductSkuUseCase
from src.application.use_cases.upload_aisle_assets import UploadAisleAssetsUseCase
from src.application.use_cases.upload_inventory_visual_references import (
    ListInventoryVisualReferencesUseCase,
    UploadInventoryVisualReferencesUseCase,
)
from src.runtime.app_container import get_app_container
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_analytics_repo,
    get_capture_session_confirm_repo,
    get_capture_session_group_repo,
    get_capture_session_item_repo,
    get_capture_session_repo,
    get_client_repo,
    get_client_supplier_repo,
    get_clock,
    get_evidence_repo,
    get_final_count_repo,
    get_inventory_repo,
    get_inventory_visual_reference_repo,
    get_job_repo,
    get_metrics_calculator,
    get_position_repo,
    get_product_record_repo,
    get_recompute_consolidated_counts_use_case,
    get_review_action_repo,
    get_source_asset_repo,
    get_worker_launch_service,
)

logger = logging.getLogger(__name__)


def get_artifact_storage():
    """Return configured artifact storage adapter (local or S3) via the app composition root."""
    return get_app_container().get_artifact_storage()


def get_worker_launch_service_dep() -> WorkerLaunchService:
    return get_worker_launch_service()


def get_job_stale_reconciler(
    job_repo: JobRepository = Depends(get_job_repo),
    clock: Clock = Depends(get_clock),
) -> JobStaleReconciler:
    from src.config import load_settings

    settings = load_settings()
    return JobStaleReconciler(
        job_repo=job_repo,
        clock=clock,
        stale_after_seconds=int(getattr(settings, "worker_stale_running_timeout_sec", 0) or 0),
    )


def get_operational_execution_config_resolver() -> OperationalExecutionConfigResolver:
    return OperationalExecutionConfigResolver()


def get_create_inventory_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
    clock: Clock = Depends(get_clock),
    operational_resolver: OperationalExecutionConfigResolver = Depends(
        get_operational_execution_config_resolver
    ),
) -> CreateInventoryUseCase:
    from src.config import load_settings as _load_settings

    return CreateInventoryUseCase(
        inventory_repo=repo,
        clock=clock,
        operational_resolver=operational_resolver,
        settings_loader=_load_settings,
    )


def get_create_client_use_case(
    repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> CreateClientUseCase:
    return CreateClientUseCase(client_repo=repo, clock=clock)


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
) -> ListInventoryListItemsUseCase:
    return ListInventoryListItemsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
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
    clock: Clock = Depends(get_clock),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
) -> CreateAisleUseCase:
    return CreateAisleUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        clock=clock,
        status_reconciler=status_reconciler,
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
    position_repo: PositionRepository = Depends(get_position_repo),
    source_asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
) -> ListAislesWithStatusUseCase:
    return ListAislesWithStatusUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        source_asset_repo=source_asset_repo,
        result_context_resolver=result_context_resolver,
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
) -> StartAisleProcessingUseCase:
    return StartAisleProcessingUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=job_repo,
        launch_service=launch_service,
        stale_reconciler=stale_reconciler,
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
) -> UploadAisleAssetsUseCase:
    return UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=artifact_storage,
        clock=clock,
        status_reconciler=status_reconciler,
    )


def get_list_aisle_assets_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
) -> ListAisleAssetsUseCase:
    return ListAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
    )


def get_delete_aisle_source_asset_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
) -> DeleteAisleSourceAssetUseCase:
    return DeleteAisleSourceAssetUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=job_repo,
        artifact_storage=artifact_storage,
        clock=clock,
        status_reconciler=status_reconciler,
    )


def get_upload_inventory_visual_references_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    reference_repo: InventoryVisualReferenceRepository = Depends(
        get_inventory_visual_reference_repo
    ),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
) -> UploadInventoryVisualReferencesUseCase:
    return UploadInventoryVisualReferencesUseCase(
        inventory_repo=inventory_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
        clock=clock,
    )


def get_list_inventory_visual_references_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    reference_repo: InventoryVisualReferenceRepository = Depends(
        get_inventory_visual_reference_repo
    ),
) -> ListInventoryVisualReferencesUseCase:
    return ListInventoryVisualReferencesUseCase(
        inventory_repo=inventory_repo,
        reference_repo=reference_repo,
    )


def get_delete_inventory_visual_reference_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    reference_repo: InventoryVisualReferenceRepository = Depends(
        get_inventory_visual_reference_repo
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> DeleteInventoryVisualReferenceUseCase:
    return DeleteInventoryVisualReferenceUseCase(
        inventory_repo=inventory_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
    )


def get_replace_inventory_visual_reference_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    reference_repo: InventoryVisualReferenceRepository = Depends(
        get_inventory_visual_reference_repo
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> ReplaceInventoryVisualReferenceUseCase:
    return ReplaceInventoryVisualReferenceUseCase(
        inventory_repo=inventory_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
    )


def get_list_aisle_positions_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
) -> ListAislePositionsUseCase:
    from src.config import load_settings

    return ListAislePositionsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        result_context_resolver=result_context_resolver,
        product_record_repo=product_record_repo,
        positions_aisle_raw_cap=load_settings().v3_positions_aisle_raw_cap,
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
) -> ResolveAisleJobForInventoryReadUseCase:
    return ResolveAisleJobForInventoryReadUseCase(job_repo=job_repo, aisle_repo=aisle_repo)


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
    return PromoteAisleOperationalJobUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
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


def get_create_capture_session_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.create_capture_session import CreateCaptureSessionUseCase
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
    from src.application.use_cases.close_capture_session import CloseCaptureSessionUseCase

    return CloseCaptureSessionUseCase(session_repo=session_repo, item_repo=item_repo, clock=clock)


def get_cancel_capture_session_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.cancel_capture_session import CancelCaptureSessionUseCase

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
    from src.application.use_cases.list_capture_sessions import ListCaptureSessionsUseCase
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
    from src.application.use_cases.get_capture_session_detail import GetCaptureSessionDetailUseCase

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
):
    from src.application.use_cases.upload_capture_session_staging_items import (
        UploadCaptureSessionStagingItemsUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    max_bytes = int(s.max_upload_size_mb) * 1024 * 1024
    return UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=artifact_storage,
        clock=clock,
        staging_prefix=s.v3_capture_staging_storage_prefix,
        max_files_per_upload=s.v3_capture_max_files_per_upload,
        max_upload_bytes=max_bytes,
        time_metadata_extractor=time_metadata_extractor,
    )


def get_update_capture_session_clock_offset_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.update_capture_session_clock_offset import (
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
    from src.application.use_cases.compute_capture_session_assignment_preview import (
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
    from src.application.use_cases.compute_capture_session_groups import (
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
    from src.application.use_cases.get_capture_session_groups import GetCaptureSessionGroupsUseCase

    return GetCaptureSessionGroupsUseCase(session_repo=session_repo, group_repo=group_repo)


def get_assign_capture_session_group_to_existing_aisle_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.assign_capture_session_group_to_existing_aisle import (
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
    from src.application.use_cases.create_aisle_and_assign_capture_session_group import (
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
    from src.application.use_cases.compute_materialized_capture_session_group_preview import (
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
    from src.application.use_cases.materialize_capture_session_group import (
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
    from src.application.use_cases.materialize_capture_session import (
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
