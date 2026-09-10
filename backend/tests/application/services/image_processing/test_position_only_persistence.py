"""POSITION_ONLY persistence: strategy result → persister → asset processor → RESOLVED."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.application.services.image_processing.asset_processing_reconciler import (
    AssetPersistCompleteness,
    AssetProcessingReconciler,
)
from src.application.services.image_processing.code_scan_asset_processor import (
    CodeScanAssetProcessor,
)
from src.application.services.image_processing.image_processing_orchestrator import (
    ImageProcessingOrchestrator,
)
from src.application.services.image_processing.processing_result_persister import (
    PersistSkipReason,
    ProcessingResultPersister,
)
from src.application.services.image_processing.vision_candidate_bridge import (
    VISION_POSITION_RAW_EVIDENCE_REQUIRED,
    normalize_vision_via_label_validation,
)
from src.application.services.position_materialization import MaterializePositionService
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.image_processing.contracts import (
    RAW_EVIDENCE_HASH_ALGORITHM,
    VISION_POSITION_DETECTOR_NAME,
    VISION_POSITION_DETECTOR_VERSION,
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
    RawEvidenceMetadata,
    VisionPositionEvidence,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.domain.position_materialization.entities import (
    MaterializePositionResult,
    PositionMaterializationAssociationStatus,
    PositionMaterializationStatus,
)
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
)
from src.domain.product_labels.processed import (
    ProcessedProductLabel,
    ProductLabelOutcomeStatus,
)
from src.infrastructure.persistence.memory_position_materialization_unit_of_work import (
    MemoryMaterializationAisle,
    MemoryMaterializationInventory,
    MemoryMaterializedLocation,
    MemoryPositionMaterializationUnitOfWork,
)
from src.infrastructure.repositories.memory_image_position_label_detection_repository import (
    MemoryImagePositionLabelDetectionRepository,
)
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)
from src.infrastructure.repositories.memory_processing_attempt_repository import (
    MemoryProcessingAttemptRepository,
)
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)

NOW = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
JOB_ID = "68aae986-4429-40d5-9da1-4646a8f7e72f"
ASSET_ID = "ad40b787-081e-4551-a733-db3d5c06e004"
AISLE_ID = "68a652c5-65f6-487d-a417-4349b8e3e81c"
INV_ID = "ec321684-5bd3-4e48-b75d-6caaf0225199"


class FixedClock:
    def now(self) -> datetime:
        return NOW


def _position_meta() -> dict:
    return {
        "position_detection_count": 1,
        "position_candidate_indexes": [0],
        "position_statuses": ["VALID"],
        "position_profile_source": "SUPPLIER",
        "normalized_positions": [
            {
                "position_id": "A04-R-02",
                "pallet": "04",
                "side": "RIGHT",
                "level": "02",
                "detection_index": 0,
            }
        ],
    }


def _position_only_result(*, evidence: dict | None = None) -> ImageProcessingResult:
    return ImageProcessingResult(
        job_id=JOB_ID,
        asset_id=ASSET_ID,
        status=ImageResultStatus.RESOLVED_INTERNAL,
        processing_mode="CODE_SCAN",
        resolved_by="CODE_SCAN",
        evidence={
            "result_kind": "POSITION_ONLY",
            "position_label_detection": _position_meta(),
            **(evidence or {}),
        },
        warnings=["POSITION_LABEL_ONLY"],
        error_code=None,
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
    )


def _vision_position_only_result(
    *,
    code: str,
    raw_code: str | None = None,
    asset_id: str = ASSET_ID,
) -> ImageProcessingResult:
    raw = code if raw_code is None else raw_code
    raw_bytes = raw.encode("utf-8")
    return ImageProcessingResult(
        job_id=JOB_ID,
        asset_id=asset_id,
        status=ImageResultStatus.RESOLVED_EXTERNAL,
        processing_mode="EXTERNAL_PROVIDER",
        resolved_by="EXTERNAL_PROVIDER",
        evidence={
            "result_kind": "POSITION_ONLY",
            "position_label_detection": {
                "position_detection_count": 1,
                "position_statuses": ["VALID"],
                "recognition_source": "VISION",
                "client_id": "client-1",
                "normalized_positions": [{"position_id": code}],
            },
        },
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
        vision_position_evidence=(
            VisionPositionEvidence(
                recognition=CanonicalPositionRecognition(
                    raw_code=raw,
                    normalized_code=code,
                    source=PositionRecognitionSource.VISION,
                ),
                client_id="client-1",
                detector_name=VISION_POSITION_DETECTOR_NAME,
                detector_version=VISION_POSITION_DETECTOR_VERSION,
                raw_evidence=RawEvidenceMetadata(
                    payload_hash=hashlib.sha256(raw_bytes).hexdigest(),
                    utf8_length=len(raw_bytes),
                    hash_algorithm=RAW_EVIDENCE_HASH_ALGORITHM,
                ),
            ),
        ),
    )


def _product_result() -> ImageProcessingResult:
    return ImageProcessingResult(
        job_id=JOB_ID,
        asset_id="item-asset-1",
        status=ImageResultStatus.RESOLVED_INTERNAL,
        processing_mode="CODE_SCAN",
        resolved_by="CODE_SCAN",
        internal_code="SKU773421",
        quantity=24.0,
        product_results=[
            ProcessedProductLabel(
                label_id="LPNA000184",
                internal_code="SKU773421",
                quantity=24,
                format_version="SUPPLIER",
                checksum=None,
                validation_status=ProductLabelOutcomeStatus.VALID,
            )
        ],
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
    )


def _link(*, job_id: str, asset_id: str) -> JobSourceAssetLink:
    return JobSourceAssetLink(
        id=f"jsa-{asset_id}",
        job_id=job_id,
        source_asset_id=asset_id,
        asset_role="primary",
        position_order=0,
        checksum=None,
        storage_key=f"key/{asset_id}.jpg",
        mime_type="image/jpeg",
        size_bytes=100,
        width=None,
        height=None,
        stage=None,
        provider_request_id=None,
        created_at=NOW,
        original_filename=f"{asset_id}.jpg",
    )


def _position_detection(
    *, job_id: str = JOB_ID, asset_id: str = ASSET_ID
) -> ImagePositionLabelDetection:
    return ImagePositionLabelDetection(
        id=str(uuid4()),
        client_id="client-1",
        inventory_id=INV_ID,
        job_id=job_id,
        source_asset_id=asset_id,
        client_image_id=None,
        ordered_capture_session_id=None,
        sequence_number=1,
        position_label_id=None,
        public_identifier="A04-R-02",
        position_name_snapshot="A04-R-02",
        payload_version=None,
        signature_status=PositionLabelSignatureStatus.SKIPPED,
        detection_status=PositionLabelDetectionStatus.VALID,
        confidence=1.0,
        bounding_box_json=None,
        rotation_degrees=None,
        raw_payload_hash="hash-a04",
        detector_name="code_scan",
        detector_version="supplier-v1",
        created_at=NOW,
        updated_at=NOW,
        metadata_json={
            "pallet": "04",
            "side": "RIGHT",
            "level": "02",
        },
    )


def _persister_harness(
    *,
    job_id: str = JOB_ID,
    asset_id: str = ASSET_ID,
    position_repo: MemoryImagePositionLabelDetectionRepository | None = None,
):
    position_repo = position_repo or MemoryImagePositionLabelDetectionRepository()
    result_evidence_repo = MemoryResultEvidenceRepository()
    saved_evidence: list = []

    job_source = MagicMock()
    job_source.list_for_job.return_value = [_link(job_id=job_id, asset_id=asset_id)]
    source_repo = MagicMock()
    source_repo.get_by_id.return_value = SimpleNamespace(
        storage_path=f"path/{asset_id}.jpg",
        storage_key=f"key/{asset_id}.jpg",
        content_type="image/jpeg",
        file_size_bytes=100,
    )

    coverage_repo = MagicMock()
    coverage_repo.get_by_job_and_asset.return_value = None
    image_coverage_repo = MagicMock()
    image_coverage_repo.has_results_for_asset.return_value = False

    position_entity_repo = MagicMock()
    product_repo = MagicMock()

    def _save_evidence(rows):
        saved_evidence.extend(rows)
        result_evidence_repo.save_many(rows)

    repos = SimpleNamespace(
        manual_coverage_repo=coverage_repo,
        image_coverage_repo=image_coverage_repo,
        position_repo=position_entity_repo,
        product_record_repo=product_repo,
        evidence_repo=MagicMock(),
        result_evidence_repo=SimpleNamespace(
            save_many=_save_evidence,
            list_by_job_id=result_evidence_repo.list_by_job_id,
        ),
        counted_product_label_repo=MagicMock(),
        materialization_receipt_repo=MagicMock(),
    )
    uow = MagicMock()
    uow.repositories = repos
    uow.__enter__ = MagicMock(return_value=uow)
    uow.__exit__ = MagicMock(return_value=False)

    persister = ProcessingResultPersister(
        job_source_asset_repo=job_source,
        source_asset_repo=source_repo,
        clock=FixedClock(),
        unit_of_work_factory=lambda: uow,
        position_detection_repo=position_repo,
    )
    return (
        persister,
        position_repo,
        result_evidence_repo,
        saved_evidence,
        product_repo,
        position_entity_repo,
    )


def _materializer(
    *,
    supplier_id: str | None = None,
    locations: list[MemoryMaterializedLocation] | None = None,
) -> tuple[MaterializePositionService, MemoryPositionMaterializationUnitOfWork]:
    uow = MemoryPositionMaterializationUnitOfWork(
        inventories=[MemoryMaterializationInventory(id=INV_ID, client_id="client-1")],
        aisles=[
            MemoryMaterializationAisle(
                id=AISLE_ID,
                inventory_id=INV_ID,
                client_supplier_id=supplier_id,
            )
        ],
        locations=locations,
    )
    return MaterializePositionService(uow, clock=lambda: NOW), uow


def test_position_only_persister_success_with_durable_detection() -> None:
    persister, position_repo, result_evidence_repo, _, product_repo, position_entity_repo = (
        _persister_harness()
    )
    det = _position_detection()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[det],
    )

    outcome = persister.persist(
        result=_position_only_result(),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )

    assert outcome.persisted is True
    assert outcome.reconciled is True
    assert outcome.skipped_reason is None
    assert outcome.products_persisted == 0
    assert outcome.positions_persisted == 1
    assert outcome.position_id == det.id
    product_repo.save.assert_not_called()
    position_entity_repo.save.assert_not_called()
    assert len(list(result_evidence_repo.list_by_job_id(JOB_ID))) == 1


def test_position_materialization_flag_off_never_calls_service() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    materializer = MagicMock()
    persister._position_materializer = materializer

    outcome = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )

    assert outcome.persisted is True
    materializer.execute.assert_not_called()


def test_dinamic_position_materializes_before_success() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    detection = _position_detection()
    detection.detector_version = "position-label-detection-1.0.0"
    detection.signature_status = PositionLabelSignatureStatus.VALID
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version=detection.detector_version,
        detections=[detection],
    )
    materializer, uow = _materializer()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    outcome = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )

    assert outcome.persisted is True
    assert len(uow.locations) == 1
    location = next(iter(uow.locations.values()))
    assert location.normalized_code == "A04-R-02"
    assert location.raw_recognition_code is None
    assert location.recognition_source == "CODE_SCAN"
    request = next(iter(uow.requests.values()))
    assert request.association_status is PositionMaterializationAssociationStatus.ASSOCIATED


def test_multiple_position_requests_are_all_associated_after_result_commit() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    first = _position_detection()
    second = _position_detection()
    second.public_identifier = "A04-R-03"
    second.position_name_snapshot = "A04-R-03"
    second.sequence_number = 2
    second.raw_payload_hash = "hash-a04-r03"
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[first, second],
    )
    materializer, uow = _materializer()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    outcome = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )

    assert outcome.persisted is True
    assert outcome.positions_persisted == 2
    assert len(uow.requests) == 2
    assert {request.association_status for request in uow.requests.values()} == {
        PositionMaterializationAssociationStatus.ASSOCIATED
    }


def test_manual_coverage_conflict_is_checked_before_materialization() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    manual_uow = persister._uow_factory()
    manual_uow.repositories.manual_coverage_repo.get_by_job_and_asset.return_value = (
        SimpleNamespace(position_id="manual-position", created_by_user_id="operator-1")
    )
    materializer = MagicMock()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    outcome = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )

    assert outcome.skipped_reason is PersistSkipReason.MANUAL_RESULT_EXISTS
    materializer.execute.assert_not_called()


def test_post_materialization_manual_race_requires_review_then_retry_associates() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    materializer, materialization_uow = _materializer()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True
    final_uow = persister._uow_factory()
    final_uow.repositories.manual_coverage_repo.get_by_job_and_asset.side_effect = [
        None,
        SimpleNamespace(position_id="manual-position", created_by_user_id="operator-1"),
        None,
        None,
    ]

    raced = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )

    assert raced.skipped_reason is PersistSkipReason.MANUAL_RESULT_EXISTS
    request = next(iter(materialization_uow.requests.values()))
    assert request.association_status is PositionMaterializationAssociationStatus.REQUIRES_REVIEW
    assert request.association_error_code == "IMAGE_MANUAL_RESULT_CONFLICT"
    assert len(materialization_uow.locations) == 1

    retry = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )

    assert retry.persisted is True
    request = next(iter(materialization_uow.requests.values()))
    assert request.association_status is PositionMaterializationAssociationStatus.ASSOCIATED
    assert request.association_error_code is None
    assert len(materialization_uow.locations) == 1
    assert len(materialization_uow.requests) == 1


def test_supplier_position_materializes_with_authoritative_scope_metadata() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    detection = _position_detection()
    detection.metadata_json.update(
        {
            "profile_source": "SUPPLIER",
            "client_supplier_id": "supplier-1",
            "profile_id": "profile-7",
            "profile_version": 3,
        }
    )
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version=detection.detector_version,
        detections=[detection],
    )
    materializer, uow = _materializer(supplier_id="supplier-1")
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    outcome = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )

    assert outcome.persisted is True
    location = next(iter(uow.locations.values()))
    assert location.client_supplier_id == "supplier-1"
    assert location.profile_id == "profile-7"
    assert location.profile_version == 3


@pytest.mark.parametrize(
    "status",
    [
        PositionMaterializationStatus.REJECTED_CONFLICT,
        PositionMaterializationStatus.REJECTED_SCOPE,
        PositionMaterializationStatus.REJECTED_INVENTORY_STATE,
        PositionMaterializationStatus.RETRYABLE_FAILURE,
    ],
)
def test_materializer_rejection_fails_without_acknowledging(
    status: PositionMaterializationStatus,
) -> None:
    persister, position_repo, result_evidence_repo, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    materializer = MagicMock()
    materializer.execute.return_value = MaterializePositionResult(status=status)
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    outcome = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )

    assert outcome.skipped_reason is PersistSkipReason.POSITION_MATERIALIZATION_FAILED
    assert list(result_evidence_repo.list_by_job_id(JOB_ID)) == []


def test_position_detection_repository_timeout_maps_to_retryable_persist_outcome() -> None:
    position_repo = MagicMock()
    position_repo.list_by_asset.side_effect = TimeoutError("repository timed out")
    persister, _, result_evidence_repo, _, _, _ = _persister_harness(position_repo=position_repo)
    materializer = MagicMock()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    outcome = persister.persist(
        result=_position_only_result(),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )

    assert outcome.skipped_reason is PersistSkipReason.POSITION_MATERIALIZATION_FAILED
    assert outcome.retryable is True
    assert list(result_evidence_repo.list_by_job_id(JOB_ID)) == []
    materializer.execute.assert_not_called()


def test_vision_position_creates_detection_and_materializes(caplog) -> None:
    persister, position_repo, _, _, product_repo, position_entity_repo = _persister_harness()
    materializer, uow = _materializer()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True
    result = _vision_position_only_result(code="A04-R-02", raw_code="a04-r-02")

    outcome = persister.persist(result=result, inventory_id=INV_ID, aisle_id=AISLE_ID)

    assert outcome.persisted is True
    rows = list(position_repo.list_by_asset(JOB_ID, ASSET_ID))
    assert len(rows) == 1
    assert rows[0].detector_version == VISION_POSITION_DETECTOR_VERSION
    assert rows[0].raw_payload_hash == hashlib.sha256(b"a04-r-02").hexdigest()
    assert "raw_payload" not in rows[0].metadata_json
    assert "a04-r-02" not in repr(rows[0].metadata_json)
    assert rows[0].metadata_json["raw_payload_length"] == len(b"a04-r-02")
    assert rows[0].metadata_json["raw_hash_algorithm"] == RAW_EVIDENCE_HASH_ALGORITHM
    assert len(uow.locations) == 1
    assert next(iter(uow.locations.values())).raw_recognition_code == "a04-r-02"
    assert "a04-r-02" not in caplog.text
    product_repo.save.assert_not_called()
    position_entity_repo.save.assert_not_called()


def test_vision_retry_replaces_stale_detection_before_materializing() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    stale = _position_detection()
    stale.public_identifier = "A-OLD"
    stale.position_name_snapshot = "A-OLD"
    stale.detector_version = VISION_POSITION_DETECTOR_VERSION
    stale.metadata_json = {"recognition_source": "VISION"}
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version=VISION_POSITION_DETECTOR_VERSION,
        detections=[stale],
    )
    materializer, uow = _materializer()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    outcome = persister.persist(
        result=_vision_position_only_result(code="B-NEW"),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )

    assert outcome.persisted is True
    rows = list(position_repo.list_by_asset(JOB_ID, ASSET_ID))
    assert [row.public_identifier for row in rows] == ["B-NEW"]
    assert {location.normalized_code for location in uow.locations.values()} == {"B-NEW"}


def test_invalid_vision_position_never_writes() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    materializer = MagicMock()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True
    invalid = _position_only_result(
        evidence={
            "position_label_detection": {
                "position_statuses": ["INVALID_FORMAT"],
                "recognition_source": "VISION",
                "client_id": "client-1",
                "normalized_positions": [{"position_id": "A04-R-02"}],
            }
        }
    )

    outcome = persister.persist(result=invalid, inventory_id=INV_ID, aisle_id=AISLE_ID)

    assert outcome.skipped_reason is PersistSkipReason.POSITION_MATERIALIZATION_FAILED
    assert list(position_repo.list_by_asset(JOB_ID, ASSET_ID)) == []
    materializer.execute.assert_not_called()


def test_structured_only_vision_position_never_reaches_materialization() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    materializer = MagicMock()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True
    result = normalize_vision_via_label_validation(
        job_id=JOB_ID,
        asset_id=ASSET_ID,
        analysis=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.VALID,
            provider_name="gemini",
            model_name="model",
            normalized_result={"position_id": "INFERRED-POSITION-SECRET"},
        ),
        validation_context=LabelValidationContext(
            resolved_profiles=None,
            client_id="client-1",
        ),
        base_fields={},
        evidence={},
    )

    outcome = persister.persist(result=result, inventory_id=INV_ID, aisle_id=AISLE_ID)

    assert result.error_code == VISION_POSITION_RAW_EVIDENCE_REQUIRED
    assert result.vision_position_evidence == ()
    assert outcome.skipped_reason is PersistSkipReason.NOT_RESOLVED_INTERNAL
    assert list(position_repo.list_by_asset(JOB_ID, ASSET_ID)) == []
    materializer.execute.assert_not_called()


def test_code_scan_and_vision_same_code_reuse_one_location() -> None:
    detection_repo = MemoryImagePositionLabelDetectionRepository()
    code_persister, _, _, _, _, _ = _persister_harness(position_repo=detection_repo)
    detection_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    materializer, uow = _materializer()
    code_persister._position_materializer = materializer
    code_persister._position_auto_materialization_enabled = True
    assert code_persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    ).persisted

    vision_asset = "bd40b787-081e-4551-a733-db3d5c06e005"
    vision_persister, _, _, _, _, _ = _persister_harness(
        asset_id=vision_asset,
        position_repo=detection_repo,
    )
    vision_persister._position_materializer = materializer
    vision_persister._position_auto_materialization_enabled = True
    vision_result = _vision_position_only_result(
        code="A04-R-02",
        raw_code=" a04-r-02 ",
        asset_id=vision_asset,
    )

    assert vision_persister.persist(
        result=vision_result, inventory_id=INV_ID, aisle_id=AISLE_ID
    ).persisted
    assert len(uow.locations) == 1
    assert len(uow.requests) == 2
    assert {request.result for request in uow.requests.values()} == {
        PositionMaterializationStatus.MATERIALIZED,
        PositionMaterializationStatus.REUSED,
    }


def test_existing_position_is_reused() -> None:
    existing = MemoryMaterializedLocation(
        id="location-existing",
        public_identifier="loc_existing",
        client_id="client-1",
        aisle_id=AISLE_ID,
        code="A04-R-02",
        normalized_code="A04-R-02",
        status="ACTIVE",
        created_by="operator",
        created_at=NOW,
        updated_at=NOW,
    )
    materializer, uow = _materializer(locations=[existing])
    persister, position_repo, _, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    assert persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    ).persisted
    assert len(uow.locations) == 1
    request = next(iter(uow.requests.values()))
    assert request.location_id == existing.id
    assert request.result is PositionMaterializationStatus.REUSED


def test_result_commit_failure_retries_same_materialized_location() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    materializer, materialization_uow = _materializer()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    manual_uow = persister._uow_factory()
    staged: list = []
    committed: list = []
    commit_calls = 0

    def save_many(rows) -> None:
        staged.extend(rows)

    def list_by_job_id(job_id: str):
        return [row for row in committed if row.job_id == job_id]

    def commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            staged.clear()
            raise RuntimeError("result transaction failed")
        committed.extend(staged)
        staged.clear()

    manual_uow.repositories.result_evidence_repo = SimpleNamespace(
        save_many=save_many,
        list_by_job_id=list_by_job_id,
    )
    manual_uow.commit.side_effect = commit

    with pytest.raises(RuntimeError, match="result transaction failed"):
        persister.persist(
            result=_position_only_result(),
            inventory_id=INV_ID,
            aisle_id=AISLE_ID,
        )
    assert len(materialization_uow.locations) == 1
    assert committed == []
    pending_request = next(iter(materialization_uow.requests.values()))
    assert pending_request.association_status is PositionMaterializationAssociationStatus.PENDING

    retry = persister.persist(
        result=_position_only_result(),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )

    assert retry.persisted is True
    assert retry.idempotent_replay is True
    assert len(materialization_uow.locations) == 1
    assert len(materialization_uow.requests) == 1
    assert len(committed) == 1
    associated_request = next(iter(materialization_uow.requests.values()))
    assert (
        associated_request.association_status is PositionMaterializationAssociationStatus.ASSOCIATED
    )


def test_committed_result_with_cas_failure_recovers_on_already_persisted_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persister, position_repo, result_evidence_repo, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    materializer, materialization_uow = _materializer()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True
    original_complete = materializer.complete_association
    completion_calls = 0

    def fail_first_completion(*args, **kwargs):
        nonlocal completion_calls
        completion_calls += 1
        if completion_calls == 1:
            return False
        return original_complete(*args, **kwargs)

    monkeypatch.setattr(materializer, "complete_association", fail_first_completion)

    first = persister.persist(
        result=_position_only_result(),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )

    assert first.persisted is True
    assert len(list(result_evidence_repo.list_by_job_id(JOB_ID))) == 1
    pending = next(iter(materialization_uow.requests.values()))
    assert pending.association_status is PositionMaterializationAssociationStatus.PENDING

    retry = persister.persist(
        result=_position_only_result(),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )

    assert retry.persisted is False
    assert retry.reconciled is True
    assert retry.skipped_reason is PersistSkipReason.ALREADY_PERSISTED
    assert retry.idempotent_replay is True
    assert completion_calls == 2
    associated = next(iter(materialization_uow.requests.values()))
    assert associated.association_status is PositionMaterializationAssociationStatus.ASSOCIATED
    assert len(materialization_uow.locations) == 1
    assert len(materialization_uow.requests) == 1


def test_pre_rollout_already_persisted_recovery_does_not_materialize() -> None:
    persister, position_repo, result_evidence_repo, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    first = persister.persist(
        result=_position_only_result(),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )
    assert first.persisted is True
    assert len(list(result_evidence_repo.list_by_job_id(JOB_ID))) == 1

    materializer, materialization_uow = _materializer()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True
    retry = persister.persist(
        result=_position_only_result(),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )

    assert retry.persisted is False
    assert retry.reconciled is True
    assert retry.skipped_reason is PersistSkipReason.ALREADY_PERSISTED
    assert materialization_uow.locations == {}
    assert materialization_uow.requests == {}


def test_position_only_without_durable_detection_fails_closed() -> None:
    persister, _, _, _, _, _ = _persister_harness()
    outcome = persister.persist(
        result=_position_only_result(),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )
    assert outcome.persisted is False
    assert outcome.skipped_reason is PersistSkipReason.POSITION_MATERIALIZATION_FAILED


def test_position_only_without_evidence_fails_closed() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    result = ImageProcessingResult(
        job_id=JOB_ID,
        asset_id=ASSET_ID,
        status=ImageResultStatus.RESOLVED_INTERNAL,
        processing_mode="CODE_SCAN",
        resolved_by="CODE_SCAN",
        evidence={"result_kind": "POSITION_ONLY"},
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
    )
    outcome = persister.persist(result=result, inventory_id=INV_ID, aisle_id=AISLE_ID)
    assert outcome.skipped_reason is PersistSkipReason.POSITION_MATERIALIZATION_FAILED


def test_product_result_still_requires_code_and_quantity() -> None:
    persister, _, _, _, _, _ = _persister_harness(job_id=JOB_ID, asset_id="item-asset-1")
    incomplete = ImageProcessingResult(
        job_id=JOB_ID,
        asset_id="item-asset-1",
        status=ImageResultStatus.RESOLVED_INTERNAL,
        processing_mode="CODE_SCAN",
        resolved_by="CODE_SCAN",
        internal_code=None,
        quantity=None,
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
    )
    outcome = persister.persist(result=incomplete, inventory_id=INV_ID, aisle_id=AISLE_ID)
    assert outcome.skipped_reason is PersistSkipReason.MISSING_CODE_OR_QUANTITY


def test_product_persist_unchanged() -> None:
    persister, _, _, _, product_repo, position_entity_repo = _persister_harness(
        job_id=JOB_ID, asset_id="item-asset-1"
    )
    job_source = MagicMock()
    job_source.list_for_job.return_value = [_link(job_id=JOB_ID, asset_id="item-asset-1")]
    persister._job_source_asset_repo = job_source

    outcome = persister.persist(
        result=_product_result(),
        inventory_id=INV_ID,
        aisle_id=AISLE_ID,
    )
    assert outcome.persisted is True
    assert outcome.products_persisted == 1
    product_repo.save.assert_called_once()
    position_entity_repo.save.assert_called_once()


def test_product_path_ignores_enabled_position_materializer() -> None:
    persister, _, _, _, product_repo, position_entity_repo = _persister_harness(
        job_id=JOB_ID, asset_id="item-asset-1"
    )
    persister._job_source_asset_repo.list_for_job.return_value = [
        _link(job_id=JOB_ID, asset_id="item-asset-1")
    ]
    materializer = MagicMock()
    persister._position_materializer = materializer
    persister._position_auto_materialization_enabled = True

    outcome = persister.persist(result=_product_result(), inventory_id=INV_ID, aisle_id=AISLE_ID)

    assert outcome.persisted is True
    product_repo.save.assert_called_once()
    position_entity_repo.save.assert_called_once()
    materializer.execute.assert_not_called()


def test_position_only_idempotent_second_persist() -> None:
    persister, position_repo, result_evidence_repo, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )
    first = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )
    second = persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )
    assert first.persisted is True
    assert second.reconciled is True
    assert second.skipped_reason is PersistSkipReason.ALREADY_PERSISTED
    assert second.idempotent_replay is False
    assert len(list(result_evidence_repo.list_by_job_id(JOB_ID))) == 1


class _PositionOnlyStrategy:
    strategy_key = "CODE_SCAN"
    attempt_provider = "code_scan"
    attempt_model = "local"

    def __init__(self, result: ImageProcessingResult) -> None:
        self._result = result

    def process(self, context, asset) -> ImageProcessingResult:
        return self._result


def test_processor_position_only_finalizes_resolved() -> None:
    position_repo = MemoryImagePositionLabelDetectionRepository()
    det = _position_detection()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[det],
    )
    persister, _, _, _, _, _ = _persister_harness(position_repo=position_repo)

    state_repo = MemoryJobAssetProcessingStateRepository()
    state = JobAssetProcessingState(
        id="st-pos",
        job_id=JOB_ID,
        asset_id=ASSET_ID,
        status=JobAssetProcessingStatus.PENDING,
        attempt_count=0,
        created_at=NOW,
        updated_at=NOW,
    )
    state_repo.save(state)

    attempt_repo = MemoryProcessingAttemptRepository()
    image_orch = ImageProcessingOrchestrator(
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        clock=FixedClock(),
        attempts_enabled=True,
    )

    proc = CodeScanAssetProcessor(
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        image_orchestrator=image_orch,
        code_scan_strategy=_PositionOnlyStrategy(_position_only_result()),
        result_persister=persister,
        clock=FixedClock(),
        attempts_enabled=True,
    )
    job = Job(
        id=JOB_ID,
        job_type="process_aisle",
        target_type="aisle",
        target_id=AISLE_ID,
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": AISLE_ID},
        created_at=NOW,
        updated_at=NOW,
    )
    aisle = Aisle(
        id=AISLE_ID,
        inventory_id=INV_ID,
        code="P6",
        status=AisleStatus.PROCESSING,
        created_at=NOW,
        updated_at=NOW,
    )
    asset = SourceAsset(
        id=ASSET_ID,
        aisle_id=AISLE_ID,
        type=SourceAssetType.PHOTO,
        original_filename="pos.jpg",
        storage_path="/pos.jpg",
        mime_type="image/jpeg",
        uploaded_at=NOW,
    )

    out = proc.process_asset(
        job=job, aisle=aisle, asset=asset, strategy_key="CODE_SCAN", worker_token="w1"
    )
    assert out.processed is True
    assert out.error is None

    final = state_repo.get_by_job_and_asset(JOB_ID, ASSET_ID)
    assert final is not None
    assert final.status is JobAssetProcessingStatus.RESOLVED
    assert final.error_code is None

    progress = state_repo.aggregate_progress(JOB_ID)
    assert progress.resolved == 1
    assert progress.manual_review == 0


def test_reconciler_finds_position_only_complete() -> None:
    position_repo = MemoryImagePositionLabelDetectionRepository()
    det = _position_detection()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[det],
    )

    persister, _, evidence_repo, _, _, _ = _persister_harness(position_repo=position_repo)
    persister.persist(result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID)

    reconciler = AssetProcessingReconciler(
        state_repo=MemoryJobAssetProcessingStateRepository(),
        clock=FixedClock(),
        result_evidence_repo=evidence_repo,
        position_detection_repo=position_repo,
    )
    lookup = reconciler.find_active_result(job_id=JOB_ID, asset_id=ASSET_ID)
    assert lookup.completeness is AssetPersistCompleteness.COMPLETE
    assert lookup.active_result_id is not None


def test_persister_uow_failure_does_not_mark_persisted() -> None:
    persister, position_repo, _, _, _, _ = _persister_harness()
    position_repo.replace_asset_detections_atomically(
        job_id=JOB_ID,
        source_asset_id=ASSET_ID,
        detector_version="supplier-v1",
        detections=[_position_detection()],
    )

    def _failing_uow():
        uow = MagicMock()
        uow.__enter__ = MagicMock(side_effect=RuntimeError("tx failed"))
        uow.__exit__ = MagicMock(return_value=False)
        return uow

    persister._uow_factory = _failing_uow
    with pytest.raises(RuntimeError):
        persister.persist(result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID)
