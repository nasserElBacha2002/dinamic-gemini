"""Unit tests for aisle position overlay onto Results position_code."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.position_reconciliation.aisle_position_overlay import (
    aisle_position_names_by_result_id,
    apply_aisle_position_to_summary,
)
from src.domain.position_reconciliation.entities import (
    AssignmentSource,
    AssignmentStatus,
    ProductPositionAssignment,
    RECONCILIATION_VERSION,
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
        sequence_number=1,
        position_label_id="label1" if name else None,
        position_name_snapshot=name,
        source_detection_id=None,
        assignment_status=status,
        assignment_reason="TEST",
        assignment_source=AssignmentSource.AUTOMATIC if name else None,
        reconciliation_id="rec1",
        reconciliation_version=RECONCILIATION_VERSION,
        created_at=now,
        updated_at=now,
    )


def test_names_by_result_only_automatic_with_name():
    names = aisle_position_names_by_result_id(
        [
            _assignment(
                result_id="r1",
                status=AssignmentStatus.ASSIGNED_AUTOMATIC,
                name="01",
            ),
            _assignment(
                result_id="r2",
                status=AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION,
                name=None,
            ),
        ]
    )
    assert names == {"r1": "01"}


def test_apply_replaces_synthetic_code_scan_id():
    class _Summary:
        def __init__(self) -> None:
            self.position_code = "job_code_scan_asset"
            self.aisle_position_assigned = False

        def model_copy(self, *, update):
            out = _Summary()
            out.position_code = update.get("position_code", self.position_code)
            out.aisle_position_assigned = update.get(
                "aisle_position_assigned", self.aisle_position_assigned
            )
            return out

    out = apply_aisle_position_to_summary(
        _Summary(),
        primary_product_id="r1",
        names_by_result_id={"r1": "02"},
    )
    assert out.position_code == "02"
    assert out.aisle_position_assigned is True
