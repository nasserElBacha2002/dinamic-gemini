"""Unit tests for Phase 5 published assignment read model."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.services.position_reconciliation.published_assignment_read_model import (
    PositionReadAvailability,
    map_assignment_to_view,
    no_reconciliation_view,
)
from src.application.services.position_reconciliation.published_assignment_reader import (
    PublishedPositionAssignmentReader,
)
from src.application.services.position_reconciliation.result_position_enrichment import (
    apply_published_assignment_to_summary,
    export_fields_from_view,
    matches_position_filters,
    partition_key_from_assignment_view,
    view_to_position_assignment_payload,
    view_to_position_payload,
)
from src.domain.position_reconciliation.entities import (
    RECONCILIATION_VERSION,
    AssignmentSource,
    AssignmentStatus,
    PositionReconciliation,
    ProductPositionAssignment,
    ReconciliationStatus,
)


def _assignment(
    *,
    result_id: str,
    status: AssignmentStatus,
    name: str | None,
) -> ProductPositionAssignment:
    now = datetime.now(timezone.utc)
    return ProductPositionAssignment(
        id=f"a-{result_id}",
        client_id="c1",
        inventory_id="inv1",
        job_id="job1",
        result_id=result_id,
        source_asset_id="asset1",
        ordered_capture_session_id=None,
        sequence_number=5,
        position_label_id="label1" if name else None,
        position_name_snapshot=name,
        source_detection_id=None,
        assignment_status=status,
        assignment_reason="TEST_REASON",
        assignment_source=AssignmentSource.AUTOMATIC if name else None,
        reconciliation_id="rec1",
        reconciliation_version=RECONCILIATION_VERSION,
        created_at=now,
        updated_at=now,
    )


def test_map_assigned_automatic():
    view = map_assignment_to_view(
        _assignment(
            result_id="r1",
            status=AssignmentStatus.ASSIGNED_AUTOMATIC,
            name="A-01",
        ),
        reconciliation_status=ReconciliationStatus.COMPLETED,
    )
    assert view.availability is PositionReadAvailability.AVAILABLE
    assert view.position is not None
    assert view.position.name == "A-01"
    assert view_to_position_payload(view) == {"id": "label1", "name": "A-01"}
    payload = view_to_position_assignment_payload(view)
    assert payload is not None
    assert payload["status"] == "ASSIGNED_AUTOMATIC"
    assert payload["source"] == "AUTOMATIC"


def test_map_unassigned_and_stale():
    view = map_assignment_to_view(
        _assignment(
            result_id="r2",
            status=AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION,
            name=None,
        ),
        reconciliation_status=ReconciliationStatus.STALE,
    )
    assert view.availability is PositionReadAvailability.RECONCILIATION_STALE
    assert view_to_position_payload(view) is None
    assert view.assignment_status == "UNASSIGNED_NO_PREVIOUS_POSITION"


def test_no_reconciliation_and_feature_disabled_export():
    view = no_reconciliation_view("r3")
    assert view.assignment_status == "NO_RECONCILIATION"
    fields = export_fields_from_view(view)
    assert fields["position_name"] is None
    assert fields["position_assignment_status"] == "NO_RECONCILIATION"


def test_reader_batch_and_filters():
    now = datetime.now(timezone.utc)
    published = PositionReconciliation(
        id="rec1",
        client_id="c1",
        inventory_id="inv1",
        job_id="job1",
        ordered_capture_session_id=None,
        input_fingerprint="fp",
        status=ReconciliationStatus.COMPLETED,
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    repo = MagicMock()
    repo.get_published_by_job.return_value = published
    repo.list_active_assignments.return_value = [
        _assignment(
            result_id="r1",
            status=AssignmentStatus.ASSIGNED_AUTOMATIC,
            name="A-01",
        ),
        _assignment(
            result_id="r2",
            status=AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION,
            name=None,
        ),
    ]
    reader = PublishedPositionAssignmentReader(reconciliation_repo=repo, enrichment_enabled=True)
    views = reader.load_for_job("job1", result_ids=["r1", "r2", "r3"])
    assert views["r1"].position is not None and views["r1"].position.name == "A-01"
    assert views["r2"].position is None
    assert views["r3"].assignment_status == "ASSIGNMENT_MISSING_FROM_PUBLISHED_REVISION"
    assert views["r3"].availability is PositionReadAvailability.INCONSISTENT
    assert matches_position_filters(views["r1"], with_position=True)
    assert not matches_position_filters(views["r2"], with_position=True)
    assert matches_position_filters(views["r2"], with_position=False)

    disabled = PublishedPositionAssignmentReader(
        reconciliation_repo=repo, enrichment_enabled=False
    ).load_for_job("job1", result_ids=["r1"])
    assert disabled["r1"].availability is PositionReadAvailability.FEATURE_DISABLED
    assert view_to_position_assignment_payload(disabled["r1"]) is None


def test_apply_enrichment_to_summary():
    class _Summary:
        def __init__(self) -> None:
            self.position_code = "synthetic"
            self.aisle_position_assigned = False
            self.position = None
            self.position_assignment = None

        def model_copy(self, *, update):
            out = _Summary()
            for k, v in update.items():
                setattr(out, k, v)
            return out

    view = map_assignment_to_view(
        _assignment(
            result_id="r1",
            status=AssignmentStatus.ASSIGNED_AUTOMATIC,
            name="02",
        ),
        reconciliation_status=ReconciliationStatus.COMPLETED,
    )
    out = apply_published_assignment_to_summary(
        _Summary(),
        primary_product_id="r1",
        views_by_result_id={"r1": view},
    )
    assert out.position_code == "02"
    assert out.aisle_position_assigned is True
    assert out.position == {"id": "label1", "name": "02"}
    assert out.position_assignment["status"] == "ASSIGNED_AUTOMATIC"


def test_partition_key_from_assignment_view():
    assigned = map_assignment_to_view(
        _assignment(
            result_id="r1",
            status=AssignmentStatus.ASSIGNED_AUTOMATIC,
            name="A-01",
        ),
        reconciliation_status=ReconciliationStatus.COMPLETED,
    )
    assert partition_key_from_assignment_view(assigned) == "label1|ASSIGNED_AUTOMATIC|TEST_REASON"
    unassigned = map_assignment_to_view(
        _assignment(
            result_id="r2",
            status=AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION,
            name=None,
        ),
        reconciliation_status=ReconciliationStatus.COMPLETED,
    )
    assert partition_key_from_assignment_view(unassigned) == "|UNASSIGNED_NO_PREVIOUS_POSITION|TEST_REASON"
    assert partition_key_from_assignment_view(None) == ""
