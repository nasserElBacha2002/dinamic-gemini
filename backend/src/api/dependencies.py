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

from src.api.deps.aisles import get_create_aisle_use_case  # noqa: F401
from src.api.deps.analytics import (  # noqa: F401
    get_analytics_cost_summary_service,
    get_analytics_query_service,
    get_compare_aisle_runs_use_case,
    get_compare_many_aisle_runs_use_case,
    get_export_aisle_benchmark_compare_csv_use_case,
    get_export_aisle_benchmark_run_csv_use_case,
    get_promote_aisle_operational_job_use_case,
)
from src.api.deps.capture import (  # noqa: F401
    get_assign_capture_session_group_to_existing_aisle_use_case,
    get_cancel_capture_session_use_case,
    get_capture_staging_time_metadata_extractor,
    get_close_capture_session_use_case,
    get_compute_capture_session_assignment_preview_use_case,
    get_compute_capture_session_groups_use_case,
    get_compute_materialized_capture_session_group_preview_use_case,
    get_create_aisle_and_assign_capture_session_group_use_case,
    get_create_capture_session_use_case,
    get_create_ordered_capture_session_use_case,
    get_get_capture_session_detail_use_case,
    get_get_capture_session_groups_use_case,
    get_get_ordered_capture_session_use_case,
    get_list_capture_sessions_use_case,
    get_materialize_capture_session_group_use_case,
    get_materialize_capture_session_use_case,
    get_seal_ordered_capture_session_use_case,
    get_update_capture_session_clock_offset_use_case,
    get_upload_capture_session_staging_items_use_case,
)
from src.api.deps.infrastructure import (  # noqa: F401
    get_aisle_location_label_artifact_repo,
    get_artifact_manifest_store,
    get_artifact_publication_outbox_store,
    get_artifact_storage,
    get_client_position_label_repo,
    get_client_supplier_label_profile_repo,
    get_finalization_assessment_service,
    get_image_position_label_detection_repo,
    get_inventory_status_reconciler,
    get_job_artifact_catalog_service,
    get_job_image_coverage_repo,
    get_job_retry_chain_service,
    get_job_source_asset_repo,
    get_job_stale_reconciler,
    get_manual_image_coverage_repo,
    get_manual_image_result_uow_factory,
    get_manual_position_override_repo,
    get_materialized_position_identity_reader,
    get_observability_metrics_service,
    get_operational_execution_config_resolver,
    get_position_reconciliation_repo,
    get_processing_event_repo,
    get_result_context_resolver,
    get_result_evidence_query_service,
    get_result_evidence_repo,
    get_run_auditability_service,
    get_supplier_extraction_profile_repo,
    get_worker_launch_service_dep,
)
from src.api.deps.inventory import (  # noqa: F401
    get_activate_supplier_extraction_profile_version_use_case,
    get_activate_supplier_prompt_config_version_use_case,
    get_client_recognition_config_use_case,
    get_clone_supplier_extraction_profile_use_case,
    get_create_client_supplier_use_case,
    get_create_client_use_case,
    get_create_inventory_use_case,
    get_create_supplier_extraction_profile_version_use_case,
    get_create_supplier_prompt_config_version_use_case,
    get_delete_supplier_reference_image_use_case,
    get_export_aisle_business_csv_use_case,
    get_export_aisle_results_csv_use_case,
    get_export_inventory_package_zip_use_case,
    get_export_inventory_results_use_case,
    get_export_inventory_summary_csv_use_case,
    get_get_active_supplier_extraction_profile_use_case,
    get_get_active_supplier_prompt_config_use_case,
    get_get_client_supplier_use_case,
    get_get_client_use_case,
    get_get_inventory_metrics_use_case,
    get_get_inventory_use_case,
    get_get_supplier_extraction_profile_by_version_use_case,
    get_get_supplier_prompt_config_use_case,
    get_get_supplier_reference_image_use_case,
    get_inventory_recognition_config_use_case,
    get_list_client_supplier_label_profiles_use_case,
    get_list_client_suppliers_use_case,
    get_list_clients_use_case,
    get_list_inventories_use_case,
    get_list_inventory_list_items_use_case,
    get_list_supplier_extraction_profiles_use_case,
    get_list_supplier_prompt_configs_use_case,
    get_list_supplier_reference_annotations_use_case,
    get_list_supplier_reference_images_use_case,
    get_raspberry_recognition_config_use_case,
    get_replace_supplier_reference_annotations_use_case,
    get_soft_delete_inventories_use_case,
    get_test_label_recognition_code_use_case,
    get_update_client_use_case,
    get_update_inventory_name_use_case,
    get_upload_supplier_reference_images_use_case,
    get_upsert_client_supplier_label_profile_use_case,
)
from src.api.deps.locations import (  # noqa: F401
    get_batch_render_aisle_location_labels_use_case,
    get_create_aisle_location_use_case,
    get_download_aisle_location_label_use_case,
    get_get_aisle_location_label_use_case,
    get_get_aisle_location_use_case,
    get_invalidate_aisle_location_label_use_case,
    get_issue_aisle_location_label_use_case,
    get_list_aisle_location_labels_use_case,
    get_list_aisle_locations_use_case,
    get_render_aisle_location_label_use_case,
    get_replace_aisle_location_label_use_case,
    get_update_aisle_location_use_case,
)
from src.api.deps.security import (  # noqa: F401
    get_access_principal,
    get_capture_session_access_policy,
    get_inventory_access_policy,
    require_capture_session_upload_scope,
    require_client_scope,
    require_inventory_client_scope,
    require_raspberry_device_token,
)

if TYPE_CHECKING:
    from src.application.use_cases.recovery.recover_aisle_processing import (
        RecoverAisleProcessingUseCase,
    )
    from src.application.use_cases.recovery.recover_stale_job import (
        RecoverStaleJobUseCase,
    )

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.clock import Clock
from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
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
)
from src.application.ports.services import WorkerLaunchService
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.application.services.aisle_identification_configuration_query import (
    AisleIdentificationConfigurationQuery,
)
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
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
from src.application.use_cases.aisles.resolve_aisle_job_for_inventory_read import (
    ResolveAisleJobForInventoryReadUseCase,
)
from src.application.use_cases.aisles.retry_aisle_job import RetryAisleJobUseCase
from src.application.use_cases.aisles.run_aisle_merge import RunAisleMergeUseCase
from src.application.use_cases.aisles.start_aisle_processing import StartAisleProcessingUseCase
from src.application.use_cases.aisles.update_aisle_code import UpdateAisleCodeUseCase
from src.application.use_cases.aisles.upload_aisle_assets import UploadAisleAssetsUseCase
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
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.runtime.app_container import get_app_container
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_client_repo,
    get_client_supplier_repo,
    get_clock,
    get_code_scan_repo,
    get_evidence_repo,
    get_final_count_repo,
    get_inventory_repo,
    get_job_repo,
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
)

logger = logging.getLogger(__name__)


















































































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


def get_position_materialization_service(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
):
    """Return the container-owned materializer shared with worker paths."""
    _ = (inventory_repo, aisle_repo, clock)
    container = get_app_container()
    return container.get_position_materialization_service()


def get_upsert_preliminary_detection_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    label_profile_repo=Depends(get_client_supplier_label_profile_repo),
    extraction_profile_repo=Depends(get_supplier_extraction_profile_repo),
    preliminary_repo=Depends(get_mobile_preliminary_detection_repo),
    clock: Clock = Depends(get_clock),
    position_materializer=Depends(get_position_materialization_service),
):
    from src.application.services.label_profile_resolver import LabelProfileResolver
    from src.application.services.position_label_detection.resolver import (
        PositionLabelResolver,
    )
    from src.application.services.position_recognition import (
        CanonicalPositionValidator,
        resolve_position_compatibility_policy,
    )
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.use_cases.aisles.upsert_preliminary_detection import (
        UpsertPreliminaryDetectionUseCase,
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
    return UpsertPreliminaryDetectionUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        preliminary_repo=preliminary_repo,
        clock=clock,
        enabled=bool(getattr(settings, "server_preliminary_detection_ingest_enabled", False)),
        canonical_position_validator=CanonicalPositionValidator(
            signing=signing,
            resolver=PositionLabelResolver(label_repo=container.get_client_position_label_repo()),
            policy=resolve_position_compatibility_policy(settings),
        ),
        position_materializer=position_materializer,
        auto_materialization_enabled=bool(settings.position_auto_materialization_enabled),
        flexible_mobile_enabled=bool(settings.position_flexible_mobile_enabled),
        label_profile_resolver=LabelProfileResolver(
            label_profile_repo=label_profile_repo,
            client_supplier_repo=client_supplier_repo,
            extraction_profile_repo=extraction_profile_repo,
        ),
    )


def get_persist_authoritative_local_code_scan_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    clock: Clock = Depends(get_clock),
    user: AuthUser = Depends(get_current_admin),
):
    from src.application.services.exact_extraction_profile_version import (
        ExactExtractionProfileVersionService,
    )
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
        exact_profile_service=ExactExtractionProfileVersionService(
            inventory_repo=c.get_inventory_repo(),
            aisle_repo=aisle_repo,
            client_supplier_repo=c.get_client_supplier_repo(),
            extraction_profile_repo=c.get_supplier_extraction_profile_repo(),
        ),
    )


def _build_preview_local_csv_import(
    *,
    inventory_repo: InventoryRepository,
    aisle_repo: AisleRepository,
    import_repo: LocalCsvImportRepository,
    clock: Clock,
    enabled: bool,
):
    from src.application.services.supplier_local_csv_row_revalidator import (
        build_supplier_local_csv_row_revalidator,
    )
    from src.application.use_cases.inventories.manage_local_csv_import import (
        PreviewLocalCsvImport,
    )

    container = get_app_container()
    return PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=clock,
        enabled=enabled,
        supplier_revalidator=build_supplier_local_csv_row_revalidator(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            client_supplier_repo=container.get_client_supplier_repo(),
            extraction_profile_repo=container.get_supplier_extraction_profile_repo(),
        ),
    )


def _build_import_canonical_position_materializer(container):
    settings = container.settings
    if not bool(getattr(settings, "position_import_materialization_enabled", False)):
        return None
    if not bool(getattr(settings, "position_flexible_import_enabled", False)):
        return None
    if not bool(getattr(settings, "position_flexible_validation_enabled", False)):
        return None
    from src.application.services.import_canonical_position_materializer import (
        ImportCanonicalPositionMaterializer,
    )

    service = container.get_position_materialization_service()
    if service is None:
        return None
    return ImportCanonicalPositionMaterializer(
        materialize_service=service,
        enabled=True,
        aisle_repo=container.get_aisle_repo(),
    )


def build_confirm_local_csv_import(
    *,
    container,
    clock: Clock,
    inventory_repo: InventoryRepository,
    aisle_repo: AisleRepository,
    position_repo: PositionRepository,
    product_record_repo: ProductRecordRepository,
    status_reconciler: InventoryStatusReconciler,
    enabled: bool | None = None,
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

    settings = container.settings
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
    canonical_materializer = _build_import_canonical_position_materializer(container)
    return ConfirmLocalCsvImport(
        import_repo=container.get_local_csv_import_repo(),
        result_writer=container.get_local_csv_result_writer(),
        clock=clock,
        enabled=(
            bool(getattr(settings, "server_csv_import_enabled", False))
            if enabled is None
            else enabled
        ),
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
        inventory_repo=inventory_repo,
        canonical_position_materializer=canonical_materializer,
        materialization_lease_sec=int(settings.local_csv_import_recovery_lease_sec),
        materialization_max_attempts=int(settings.local_csv_import_recovery_max_attempts),
    )


def get_preview_local_csv_import_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
):
    from src.config import load_settings

    settings = load_settings()
    return _build_preview_local_csv_import(
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
    return build_confirm_local_csv_import(
        container=get_app_container(),
        clock=clock,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
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

    from src.application.use_cases.inventories.manage_local_inventory_package import (
        PreviewLocalInventoryPackage,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    csv_repo = container.get_local_csv_import_repo()
    csv_preview = _build_preview_local_csv_import(
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
        inventory_repo=inventory_repo,
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
        canonical_position_materializer=_build_import_canonical_position_materializer(
            container
        ),
        materialization_lease_sec=int(settings.local_csv_import_recovery_lease_sec),
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
    from src.application.services.label_profile_resolver import LabelProfileResolver
    from src.application.use_cases.inventories.manage_dinamic_scanner_txt_import import (
        PreviewDinamicScannerTxtImport,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    csv_preview = _build_preview_local_csv_import(
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
    label_profile_resolver = LabelProfileResolver(
        label_profile_repo=container.get_client_supplier_label_profile_repo(),
        client_supplier_repo=client_supplier_repo,
        extraction_profile_repo=container.get_supplier_extraction_profile_repo(),
    )
    return PreviewDinamicScannerTxtImport(
        inventory_repo=inventory_repo,
        aisle_resolver=aisle_resolver,
        import_repo=container.get_local_csv_import_repo(),
        csv_preview=csv_preview,
        clock=clock,
        enabled=_dinamic_scanner_txt_import_enabled(settings),
        max_lines=int(getattr(settings, "server_dinamic_scanner_txt_max_lines", 50_000)),
        max_line_length=int(getattr(settings, "server_dinamic_scanner_txt_max_line_length", 512)),
        label_profile_resolver=label_profile_resolver,
        extraction_profile_repo=container.get_supplier_extraction_profile_repo(),
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
    from src.application.use_cases.inventories.manage_dinamic_scanner_txt_import import (
        ConfirmDinamicScannerTxtImport,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    csv_confirm = build_confirm_local_csv_import(
        container=container,
        clock=clock,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        status_reconciler=status_reconciler,
        enabled=_csv_import_pipeline_enabled(settings),
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
        enabled=bool(getattr(settings, "server_authoritative_aisle_finalization_enabled", False)),
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
    enabled = bool(getattr(settings, "server_authoritative_aisle_finalization_enabled", False))
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
    metrics_enabled = bool(getattr(settings, "preliminary_reconciliation_metrics_enabled", False))
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
        enabled=bool(getattr(settings, "server_preliminary_reconciliation_enabled", False)),
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
    principal: AccessPrincipal = Depends(get_access_principal),
    position_materializer=Depends(get_position_materialization_service),
) -> UpdatePositionCodeUseCase:
    from src.application.services.position_label_detection.resolver import (
        PositionLabelResolver,
    )
    from src.application.services.position_recognition import (
        AcceptPositionCoordinator,
        CanonicalPositionValidator,
        resolve_position_compatibility_policy,
    )
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.config import load_settings

    settings = load_settings()
    flexible_review = bool(settings.position_flexible_review_enabled)
    validator = None
    accept_coordinator = None
    if flexible_review:
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
        validator = CanonicalPositionValidator(
            signing=signing,
            resolver=PositionLabelResolver(
                label_repo=container.get_client_position_label_repo()
            ),
            policy=resolve_position_compatibility_policy(settings),
        )
        accept_coordinator = AcceptPositionCoordinator(
            settings=settings,
            auto_materialization_enabled=bool(settings.position_auto_materialization_enabled),
            materializer=position_materializer,
        )
    return UpdatePositionCodeUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=aisle_review_sync,
        principal=principal,
        canonical_position_validator=validator,
        accept_coordinator=accept_coordinator,
        position_materializer=position_materializer if flexible_review else None,
        flexible_review_enabled=flexible_review,
        auto_materialization_enabled=bool(settings.position_auto_materialization_enabled),
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
    materialized_identity_reader=Depends(get_materialized_position_identity_reader),
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
        materialized_identity_reader=(
            materialized_identity_reader if settings.position_auto_materialization_enabled else None
        ),
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
        materialized_identity_reader=get_app_container().get_materialized_position_identity_reader(),
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
