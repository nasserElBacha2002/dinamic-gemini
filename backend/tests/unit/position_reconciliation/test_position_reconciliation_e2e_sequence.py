"""Phase 4 E2E-style reconciliation against in-memory repos (ordered A→products→B→product)."""

from __future__ import annotations

from uuid import uuid4

from src.application.services.position_reconciliation.sequential_reconciler import (
    SequentialPositionReconciler,
)
from src.domain.position_label_detection.entities import (
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.domain.position_reconciliation.entities import (
    AssignmentStatus,
    ItemResultRef,
    OrderedImageFrame,
    PositionDetectionRef,
)


def _det(
    *,
    label_id: str,
    name: str,
    client_id: str,
    status: PositionLabelDetectionStatus = PositionLabelDetectionStatus.VALID,
    signature: PositionLabelSignatureStatus = PositionLabelSignatureStatus.VALID,
) -> PositionDetectionRef:
    return PositionDetectionRef(
        id=str(uuid4()),
        client_id=client_id,
        detection_status=status,
        signature_status=signature,
        position_label_id=label_id if status is PositionLabelDetectionStatus.VALID else None,
        position_name_snapshot=name if status is PositionLabelDetectionStatus.VALID else None,
        detector_version="position-label-detection-1.0.0",
    )


def test_e2e_sequence_a_xy_b_z():
    client = "client-1"
    label_a = "label-a"
    label_b = "label-b"
    frames = [
        OrderedImageFrame(
            source_asset_id="a1",
            client_image_id="c1",
            ordered_capture_session_id="sess-1",
            sequence_number=1,
            item_results=(),
            position_detections=(_det(label_id=label_a, name="A-01", client_id=client),),
        ),
        OrderedImageFrame(
            source_asset_id="a2",
            client_image_id="c2",
            ordered_capture_session_id="sess-1",
            sequence_number=2,
            item_results=(ItemResultRef(result_id="prod-x"),),
            position_detections=(),
        ),
        OrderedImageFrame(
            source_asset_id="a3",
            client_image_id="c3",
            ordered_capture_session_id="sess-1",
            sequence_number=3,
            item_results=(ItemResultRef(result_id="prod-y"),),
            position_detections=(),
        ),
        OrderedImageFrame(
            source_asset_id="a4",
            client_image_id="c4",
            ordered_capture_session_id="sess-1",
            sequence_number=4,
            item_results=(),
            position_detections=(_det(label_id=label_b, name="A-02", client_id=client),),
        ),
        OrderedImageFrame(
            source_asset_id="a5",
            client_image_id="c5",
            ordered_capture_session_id="sess-1",
            sequence_number=5,
            item_results=(ItemResultRef(result_id="prod-z"),),
            position_detections=(),
        ),
    ]
    decisions = SequentialPositionReconciler().reconcile(frames, expected_client_id=client)
    by_id = {d.result_id: d for d in decisions}
    assert by_id["prod-x"].position_label_id == label_a
    assert by_id["prod-y"].position_label_id == label_a
    assert by_id["prod-z"].position_label_id == label_b
    assert by_id["prod-x"].assignment_status is AssignmentStatus.ASSIGNED_AUTOMATIC
    assert by_id["prod-z"].position_name_snapshot == "A-02"


def test_e2e_same_image_and_before_first_and_ambiguous():
    client = "client-1"
    frames = [
        OrderedImageFrame(
            source_asset_id="a0",
            client_image_id="c0",
            ordered_capture_session_id="sess-1",
            sequence_number=1,
            item_results=(ItemResultRef(result_id="early"),),
            position_detections=(),
        ),
        OrderedImageFrame(
            source_asset_id="a1",
            client_image_id="c1",
            ordered_capture_session_id="sess-1",
            sequence_number=2,
            item_results=(ItemResultRef(result_id="same"),),
            position_detections=(_det(label_id="la", name="A-03", client_id=client),),
        ),
        OrderedImageFrame(
            source_asset_id="a2",
            client_image_id="c2",
            ordered_capture_session_id="sess-1",
            sequence_number=3,
            item_results=(),
            position_detections=(
                _det(
                    label_id="x",
                    name="?",
                    client_id=client,
                    status=PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION,
                    signature=PositionLabelSignatureStatus.VALID,
                ),
            ),
        ),
        OrderedImageFrame(
            source_asset_id="a3",
            client_image_id="c3",
            ordered_capture_session_id="sess-1",
            sequence_number=4,
            item_results=(ItemResultRef(result_id="after-amb"),),
            position_detections=(),
        ),
    ]
    decisions = SequentialPositionReconciler().reconcile(frames, expected_client_id=client)
    by_id = {d.result_id: d for d in decisions}
    assert by_id["early"].assignment_status is AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION
    assert by_id["same"].position_label_id == "la"
    assert (
        by_id["after-amb"].assignment_status
        is AssignmentStatus.UNASSIGNED_AFTER_AMBIGUOUS_POSITION
    )
