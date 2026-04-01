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
from pathlib import Path

from fastapi import Depends

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    InventoryVisualReferenceRepository,
    JobRepository,
    SourceAssetRepository,
)
from src.application.ports.repositories import (
    EvidenceRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
)
from src.application.ports.services import MetricsCalculator, WorkerLaunchService
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_analytics_repo,
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
from src.application.use_cases.create_aisle import CreateAisleUseCase
from src.application.use_cases.create_inventory import CreateInventoryUseCase
from src.application.use_cases.export_inventory_results import ExportInventoryResultsUseCase
from src.application.use_cases.get_aisle_processing_status import GetAisleProcessingStatusUseCase
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.get_inventory_metrics import GetInventoryMetricsUseCase
from src.application.use_cases.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.list_aisles_by_inventory import ListAislesByInventoryUseCase
from src.application.use_cases.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.list_aisle_positions import ListAislePositionsUseCase
from src.application.use_cases.list_review_queue import ListReviewQueueUseCase
from src.application.use_cases.get_position_detail import GetPositionDetailUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase
from src.application.use_cases.list_inventory_list_items import ListInventoryListItemsUseCase
from src.application.use_cases.confirm_position import ConfirmPositionUseCase
from src.application.use_cases.update_product_quantity import UpdateProductQuantityUseCase
from src.application.use_cases.update_product_sku import UpdateProductSkuUseCase
from src.application.use_cases.delete_position import DeletePositionUseCase
from src.application.use_cases.persist_aisle_result import PersistAisleResultUseCase
from src.application.use_cases.start_aisle_processing import StartAisleProcessingUseCase
from src.application.use_cases.retry_aisle_job import RetryAisleJobUseCase
from src.application.use_cases.upload_aisle_assets import UploadAisleAssetsUseCase
from src.application.use_cases.upload_inventory_visual_references import (
    ListInventoryVisualReferencesUseCase,
    UploadInventoryVisualReferencesUseCase,
)
from src.application.use_cases.manage_inventory_visual_references import (
    DeleteInventoryVisualReferenceUseCase,
    ReplaceInventoryVisualReferenceUseCase,
)
from src.application.use_cases.cancel_aisle_job import CancelAisleJobUseCase
from src.application.use_cases.get_aisle_merge_results import (
    GetAisleMergeResultsUseCase,
)
from src.application.services.analytics_query_service import AnalyticsQueryService
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.use_cases.run_aisle_merge import RunAisleMergeUseCase

logger = logging.getLogger(__name__)
_artifact_storage_instance = None


def get_artifact_storage():
    """Return configured artifact storage adapter (local or S3)."""
    global _artifact_storage_instance
    if _artifact_storage_instance is not None:
        return _artifact_storage_instance
    from src.config import load_settings

    settings = load_settings()
    provider = (settings.artifact_storage_provider or "local").strip().lower()
    if provider == "s3":
        from src.infrastructure.storage.s3_artifact_storage_adapter import S3ArtifactStorageAdapter

        if not settings.artifact_s3_bucket:
            raise RuntimeError("ARTIFACT_S3_BUCKET is required when ARTIFACT_STORAGE_PROVIDER=s3")
        _artifact_storage_instance = S3ArtifactStorageAdapter(
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
        return _artifact_storage_instance

    from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter

    base = Path(settings.output_dir) / "v3_uploads"
    base.mkdir(parents=True, exist_ok=True)
    _artifact_storage_instance = V3ArtifactStorageAdapter(base)
    logger.info(
        "Artifact storage configured: provider=local base_path=%s legacy_local_read=%s",
        str(base),
        settings.artifact_storage_legacy_local_read_enabled,
    )
    return _artifact_storage_instance


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


def get_create_inventory_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
    clock: Clock = Depends(get_clock),
) -> CreateInventoryUseCase:
    return CreateInventoryUseCase(inventory_repo=repo, clock=clock)


def get_list_inventories_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
) -> ListInventoriesUseCase:
    return ListInventoriesUseCase(inventory_repo=repo)


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


def get_get_inventory_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
) -> GetInventoryUseCase:
    return GetInventoryUseCase(inventory_repo=repo)


def get_export_inventory_results_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
) -> ExportInventoryResultsUseCase:
    return ExportInventoryResultsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
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
) -> ListAislesWithStatusUseCase:
    return ListAislesWithStatusUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        source_asset_repo=source_asset_repo,
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
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    launch_service: AisleJobLaunchService = Depends(get_aisle_job_launch_service),
    stale_reconciler: JobStaleReconciler = Depends(get_job_stale_reconciler),
) -> StartAisleProcessingUseCase:
    return StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
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


def get_upload_inventory_visual_references_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    reference_repo: InventoryVisualReferenceRepository = Depends(get_inventory_visual_reference_repo),
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
    reference_repo: InventoryVisualReferenceRepository = Depends(get_inventory_visual_reference_repo),
) -> ListInventoryVisualReferencesUseCase:
    return ListInventoryVisualReferencesUseCase(
        inventory_repo=inventory_repo,
        reference_repo=reference_repo,
    )


def get_delete_inventory_visual_reference_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    reference_repo: InventoryVisualReferenceRepository = Depends(get_inventory_visual_reference_repo),
    artifact_storage=Depends(get_artifact_storage),
) -> DeleteInventoryVisualReferenceUseCase:
    return DeleteInventoryVisualReferenceUseCase(
        inventory_repo=inventory_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
    )


def get_replace_inventory_visual_reference_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    reference_repo: InventoryVisualReferenceRepository = Depends(get_inventory_visual_reference_repo),
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
) -> ListAislePositionsUseCase:
    from src.config import load_settings

    return ListAislePositionsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
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
) -> GetPositionDetailUseCase:
    from src.config import load_settings

    return GetPositionDetailUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        evidence_repo=evidence_repo,
        review_repo=review_repo,
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
    recompute_uc=Depends(get_recompute_consolidated_counts_use_case),
) -> RunAisleMergeUseCase:
    return RunAisleMergeUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        recompute_use_case=recompute_uc,
    )


def get_get_aisle_merge_results_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    final_count_repo=Depends(get_final_count_repo),
) -> GetAisleMergeResultsUseCase:
    return GetAisleMergeResultsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        final_count_repo=final_count_repo,
    )


def get_analytics_query_service(
    repo=Depends(get_analytics_repo),
) -> AnalyticsQueryService:
    return AnalyticsQueryService(repo)
