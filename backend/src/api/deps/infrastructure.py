"""Cross-cutting FastAPI providers used by the public dependency facade."""

from __future__ import annotations

from fastapi import Depends

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    SourceAssetRepository,
)
from src.application.ports.services import WorkerLaunchService
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.operational_execution_config_resolver import (
    OperationalExecutionConfigResolver,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.runtime.app_container import get_app_container
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_clock,
    get_inventory_repo,
    get_job_repo,
    get_position_repo,
    get_source_asset_repo,
    get_worker_launch_service,
)
from src.runtime.v3_deps import get_artifact_manifest_store as _get_artifact_manifest_store
from src.runtime.v3_deps import (
    get_artifact_publication_outbox_store as _get_artifact_publication_outbox_store,
)
from src.runtime.v3_deps import (
    get_finalization_assessment_service as _get_finalization_assessment_service,
)
from src.runtime.v3_deps import get_result_evidence_repo as _get_result_evidence_repo


def get_artifact_storage():
    """Return configured artifact storage adapter (local or S3) via the app composition root."""
    return get_app_container().get_artifact_storage()


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


def get_result_context_resolver(
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
) -> ResultContextResolver:
    return ResultContextResolver(job_repo=job_repo, position_repo=position_repo)


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


def get_job_source_asset_repo():
    return get_app_container().get_job_source_asset_repo()


def get_manual_image_coverage_repo():
    return get_app_container().get_manual_image_coverage_repo()


def get_job_image_coverage_repo():
    return get_app_container().get_job_image_coverage_repo()


def get_manual_image_result_uow_factory():
    return get_app_container().get_manual_image_result_uow_factory()


def get_processing_event_repo():
    return get_app_container().get_processing_event_repo()


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


def get_aisle_location_label_artifact_repo():
    return get_app_container().get_aisle_location_label_artifact_repo()


def get_image_position_label_detection_repo():
    return get_app_container().get_image_position_label_detection_repo()


def get_position_reconciliation_repo():
    return get_app_container().get_position_reconciliation_repo()


def get_materialized_position_identity_reader():
    return get_app_container().get_materialized_position_identity_reader()


def get_client_position_label_repo():
    return get_app_container().get_client_position_label_repo()


def get_manual_position_override_repo():
    return get_app_container().get_manual_position_override_repo()
