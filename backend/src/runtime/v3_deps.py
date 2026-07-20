"""
Shared v3 dependency getters — used by API (via Depends) and worker.

Phase 1: wiring is delegated to :func:`src.runtime.app_container.get_app_container`.
This module keeps stable import paths (``get_inventory_repo``, etc.) for FastAPI overrides
and worker bootstrap without duplicating construction logic.
"""

from __future__ import annotations

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
    ResultEvidenceRepository,
    ReviewActionRepository,
    SourceAssetRepository,
    SupplierPromptConfigRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.services import MetricsCalculator, WorkerLaunchService
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
    SupplierReferenceAnnotationRepository,
)
from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.runtime.app_container import get_app_container


def get_inventory_repo() -> InventoryRepository:
    return get_app_container().get_inventory_repo()


def get_client_repo() -> ClientRepository:
    return get_app_container().get_client_repo()


def get_client_supplier_repo() -> ClientSupplierRepository:
    return get_app_container().get_client_supplier_repo()


def get_aisle_repo() -> AisleRepository:
    return get_app_container().get_aisle_repo()


def get_job_repo() -> JobRepository:
    return get_app_container().get_job_repo()


def get_source_asset_repo() -> SourceAssetRepository:
    return get_app_container().get_source_asset_repo()


def get_code_scan_repo() -> CodeScanRepository:
    return get_app_container().get_code_scan_repo()


def get_supplier_reference_image_repo() -> SupplierReferenceImageRepository:
    return get_app_container().get_supplier_reference_image_repo()


def get_supplier_prompt_config_repo() -> SupplierPromptConfigRepository:
    return get_app_container().get_supplier_prompt_config_repo()


def get_supplier_extraction_profile_repo() -> SupplierExtractionProfileRepository:
    return get_app_container().get_supplier_extraction_profile_repo()


def get_supplier_reference_annotation_repo() -> SupplierReferenceAnnotationRepository:
    return get_app_container().get_supplier_reference_annotation_repo()

def get_position_repo() -> PositionRepository:
    return get_app_container().get_position_repo()


def get_product_record_repo() -> ProductRecordRepository:
    return get_app_container().get_product_record_repo()


def get_evidence_repo() -> EvidenceRepository:
    return get_app_container().get_evidence_repo()


def get_result_evidence_repo() -> ResultEvidenceRepository:
    return get_app_container().get_result_evidence_repo()


def get_review_action_repo() -> ReviewActionRepository:
    return get_app_container().get_review_action_repo()


def get_metrics_calculator() -> MetricsCalculator:
    return get_app_container().get_metrics_calculator()


def get_clock() -> Clock:
    return get_app_container().get_clock()


def get_artifact_store():
    """Runtime artifact store (alias of container artifact storage — worker compatibility name)."""
    return get_app_container().get_artifact_storage()


def get_stored_artifact_reader() -> StoredArtifactReader:
    """Best-effort hybrid report / stored JSON reads (application port; no API imports)."""
    return get_app_container().get_stored_artifact_reader()


def get_worker_launch_service() -> WorkerLaunchService:
    return get_app_container().get_worker_launch_service()


def get_raw_label_repo() -> RawLabelRepository:
    return get_app_container().get_raw_label_repo()


def get_normalized_label_repo() -> NormalizedLabelRepository:
    return get_app_container().get_normalized_label_repo()


def get_final_count_repo() -> FinalCountRepository:
    return get_app_container().get_final_count_repo()


def get_analytics_repo():
    return get_app_container().get_analytics_repo()


def get_capture_session_repo() -> CaptureSessionRepository:
    return get_app_container().get_capture_session_repo()


def get_capture_session_item_repo() -> CaptureSessionItemRepository:
    return get_app_container().get_capture_session_item_repo()


def get_capture_session_group_repo() -> CaptureSessionGroupRepository:
    return get_app_container().get_capture_session_group_repo()


def get_capture_session_confirm_repo() -> CaptureSessionConfirmIdempotencyRepository:
    return get_app_container().get_capture_session_confirm_repo()


def get_recompute_consolidated_counts_use_case():
    return get_app_container().get_recompute_consolidated_counts_use_case()


def get_job_result_uow_factory():
    return get_app_container().get_job_result_uow_factory()


def get_job_scoped_recompute_factory():
    return get_app_container().get_job_scoped_recompute_factory()


def get_operational_result_promotion_service():
    return get_app_container().get_operational_result_promotion_service()


def get_finalization_stage_store():
    return get_app_container().get_finalization_stage_store()


def get_artifact_manifest_store():
    return get_app_container().get_artifact_manifest_store()


def get_job_source_asset_repo():
    return get_app_container().get_job_source_asset_repo()


def get_artifact_publication_outbox_store():
    return get_app_container().get_artifact_publication_outbox_store()


def get_artifact_staging_store():
    return get_app_container().get_artifact_staging_store()


def get_artifact_publication_dispatcher():
    return get_app_container().get_artifact_publication_dispatcher()


def get_finalization_assessment_service() -> FinalizationAssessmentService:
    return get_app_container().get_finalization_assessment_service()


def get_finalization_recovery_coordinator():
    return get_app_container().get_finalization_recovery_coordinator()
