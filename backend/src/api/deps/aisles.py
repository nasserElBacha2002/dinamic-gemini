"""Aisle lifecycle, processing orchestration, and related API dependency providers.

Implementation is mechanically extracted from src.api.dependencies. The
historical module remains the public compatibility facade.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from src.api.deps.infrastructure import (
    get_artifact_storage,
    get_client_supplier_label_profile_repo,
    get_inventory_status_reconciler,
    get_job_stale_reconciler,
    get_position_materialization_service,
    get_result_context_resolver,
    get_supplier_extraction_profile_repo,
    get_worker_launch_service_dep,
)
from src.api.deps.security import get_inventory_access_policy
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    ClientSupplierRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
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
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.runtime.app_container import get_app_container
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_client_repo,
    get_client_supplier_repo,
    get_clock,
    get_final_count_repo,
    get_inventory_repo,
    get_job_repo,
    get_mobile_preliminary_detection_repo,
    get_ordered_capture_processing_reservation,
    get_ordered_capture_session_repo,
    get_position_repo,
    get_preliminary_detection_reconciliation_repo,
    get_recompute_consolidated_counts_use_case,
    get_source_asset_repo,
    get_supplier_prompt_config_repo,
)

if TYPE_CHECKING:
    from src.application.use_cases.recovery.recover_aisle_processing import (
        RecoverAisleProcessingUseCase,
    )
    from src.application.use_cases.recovery.recover_stale_job import RecoverStaleJobUseCase


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
