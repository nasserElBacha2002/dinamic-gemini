from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.application.errors import (
    PositionReconciliationConcurrentUpdateError,
    PositionReconciliationNotReadyError,
)
from src.application.services.position_reconciliation.fingerprint import (
    build_fingerprint_from_frames,
)
from src.application.services.position_reconciliation.readiness import (
    PositionReconciliationReadinessPolicy,
)
from src.domain.jobs.entities import JobStatus
from src.domain.position_reconciliation.entities import (
    AssignmentStatus,
    ItemResultRef,
    OrderedImageFrame,
    PositionDetectionRef,
    PositionReconciliation,
    ProductPositionAssignment,
    ReconciliationStatus,
)
from src.infrastructure.repositories.memory_position_reconciliation_repository import (
    MemoryPositionReconciliationRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _frame(*, label: str = "label-1", result: str = "result-1") -> OrderedImageFrame:
    return OrderedImageFrame(
        source_asset_id="asset-1",
        client_image_id="client-image-1",
        ordered_capture_session_id="session-1",
        sequence_number=1,
        item_results=(ItemResultRef(result_id=result),),
        position_detections=(
            PositionDetectionRef(
                id="detection-1",
                client_id="client-1",
                detection_status="VALID",
                signature_status="VALID",
                position_label_id=label,
                detector_version="detector-1",
            ),
        ),
    )


def _reconciliation(
    reconciliation_id: str,
    fingerprint: str,
    *,
    status: ReconciliationStatus = ReconciliationStatus.COMPLETED,
) -> PositionReconciliation:
    return PositionReconciliation(
        id=reconciliation_id,
        client_id="client-1",
        inventory_id="inventory-1",
        job_id="job-1",
        ordered_capture_session_id="session-1",
        input_fingerprint=fingerprint,
        status=status,
        started_at=NOW,
        completed_at=NOW if status is not ReconciliationStatus.RUNNING else None,
        created_at=NOW,
        updated_at=NOW,
        is_active=status is ReconciliationStatus.COMPLETED,
    )


def _assignment(reconciliation_id: str) -> ProductPositionAssignment:
    return ProductPositionAssignment(
        id=f"assignment-{reconciliation_id}",
        client_id="client-1",
        inventory_id="inventory-1",
        job_id="job-1",
        result_id="result-1",
        source_asset_id="asset-1",
        ordered_capture_session_id="session-1",
        sequence_number=1,
        assignment_status=AssignmentStatus.ASSIGNED_AUTOMATIC,
        assignment_reason="LAST_VALID_POSITION",
        reconciliation_id=reconciliation_id,
        reconciliation_version="1.0.0",
        created_at=NOW,
        updated_at=NOW,
        position_label_id="label-1",
        source_detection_id="detection-1",
    )


def test_semantic_fingerprint_changes_for_label_and_result_set():
    baseline = build_fingerprint_from_frames([_frame()], sequence_version=1)
    assert baseline != build_fingerprint_from_frames(
        [_frame(label="label-2")], sequence_version=1
    )
    assert baseline != build_fingerprint_from_frames(
        [_frame(result="result-2")], sequence_version=1
    )
    assert baseline != build_fingerprint_from_frames([_frame()], sequence_version=2)


def test_readiness_requires_success_unless_finalizing():
    policy = PositionReconciliationReadinessPolicy()
    job = SimpleNamespace(
        id="job-1",
        status=JobStatus.RUNNING,
        ordered_capture_session_id=None,
    )
    aisle = SimpleNamespace(id="aisle-1", inventory_id="inventory-1")
    with pytest.raises(PositionReconciliationNotReadyError):
        policy.require_ready(
            job, inventory_id="inventory-1", aisle=aisle, links=[object()]
        )
    policy.require_ready(
        job,
        inventory_id="inventory-1",
        aisle=aisle,
        links=[object()],
        allow_in_finalization=True,
    )


def test_readiness_accepts_completed_ordered_session_after_code_scan_finalize():
    """CODE_SCAN marks ordered session COMPLETED before auto-reconcile runs."""
    from src.domain.ordered_capture.entities import OrderedCaptureSessionStatus

    sessions = {
        "ocs-1": SimpleNamespace(
            id="ocs-1",
            status=OrderedCaptureSessionStatus.COMPLETED,
        )
    }
    policy = PositionReconciliationReadinessPolicy(
        session_repo=SimpleNamespace(get_by_id=lambda sid: sessions.get(sid))
    )
    job = SimpleNamespace(
        id="job-1",
        status=JobStatus.SUCCEEDED,
        ordered_capture_session_id="ocs-1",
    )
    aisle = SimpleNamespace(id="aisle-1", inventory_id="inventory-1")
    policy.require_ready(
        job, inventory_id="inventory-1", aisle=aisle, links=[object()]
    )


def test_readiness_rejects_processing_ordered_session():
    from src.domain.ordered_capture.entities import OrderedCaptureSessionStatus

    sessions = {
        "ocs-1": SimpleNamespace(
            id="ocs-1",
            status=OrderedCaptureSessionStatus.PROCESSING,
        )
    }
    policy = PositionReconciliationReadinessPolicy(
        session_repo=SimpleNamespace(get_by_id=lambda sid: sessions.get(sid))
    )
    job = SimpleNamespace(
        id="job-1",
        status=JobStatus.SUCCEEDED,
        ordered_capture_session_id="ocs-1",
    )
    aisle = SimpleNamespace(id="aisle-1", inventory_id="inventory-1")
    with pytest.raises(PositionReconciliationNotReadyError, match="SEALED or COMPLETED"):
        policy.require_ready(
            job, inventory_id="inventory-1", aisle=aisle, links=[object()]
        )


def test_failed_attempt_preserves_published_assignments_and_cas_conflicts():
    repo = MemoryPositionReconciliationRepository()
    published = _reconciliation("published", "fingerprint-1")
    repo.publish_completed_revision_atomically(
        published, [_assignment(published.id)], None, published.input_fingerprint
    )
    failed = _reconciliation(
        "failed", "fingerprint-2", status=ReconciliationStatus.FAILED
    )
    repo.record_failed_attempt(failed)
    assert repo.get_published_by_job("job-1") is published
    assert [row.id for row in repo.list_active_assignments("job-1")] == [
        "assignment-published"
    ]

    replacement = _reconciliation("replacement", "fingerprint-3")
    with pytest.raises(PositionReconciliationConcurrentUpdateError):
        repo.publish_completed_revision_atomically(
            replacement,
            [_assignment(replacement.id)],
            "wrong-active-id",
            replacement.input_fingerprint,
        )
