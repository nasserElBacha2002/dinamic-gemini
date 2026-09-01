"""POSITION_ONLY persistence: strategy result → persister → asset processor → RESOLVED."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

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
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.domain.product_labels.processed import (
    ProcessedProductLabel,
    ProductLabelOutcomeStatus,
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


def _position_detection(*, job_id: str = JOB_ID, asset_id: str = ASSET_ID) -> ImagePositionLabelDetection:
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
    return persister, position_repo, result_evidence_repo, saved_evidence, product_repo, position_entity_repo


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
    persister, _, _, _, _, _ = _persister_harness(
        job_id=JOB_ID, asset_id="item-asset-1"
    )
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
    outcome = persister.persist(
        result=incomplete, inventory_id=INV_ID, aisle_id=AISLE_ID
    )
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
    persister.persist(
        result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
    )

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
        persister.persist(
            result=_position_only_result(), inventory_id=INV_ID, aisle_id=AISLE_ID
        )
