import pytest

from src.application.errors import (
    PositionReconciliationSequenceInvalidError,
    PositionReconciliationSessionMismatchError,
)
from src.application.services.position_reconciliation.sequential_reconciler import (
    SequentialPositionReconciler,
)
from src.domain.position_reconciliation.entities import (
    AssignmentStatus,
    ItemResultRef,
    OrderedImageFrame,
    PositionDetectionRef,
)


def detection(
    status="VALID",
    *,
    detection_id="d1",
    client_id="client-1",
    signature="VALID",
    label_id="label-1",
):
    return PositionDetectionRef(
        id=detection_id,
        client_id=client_id,
        detection_status=status,
        signature_status=signature,
        position_label_id=label_id,
        position_name_snapshot=label_id,
    )


def frame(
    sequence,
    *,
    asset=None,
    items=(),
    detections=(),
    session="session-1",
):
    return OrderedImageFrame(
        source_asset_id=asset or f"asset-{sequence}",
        client_image_id=asset,
        ordered_capture_session_id=session,
        sequence_number=sequence,
        item_results=tuple(ItemResultRef(result_id=item) for item in items),
        position_detections=tuple(detections),
    )


def reconcile(frames):
    return SequentialPositionReconciler().reconcile(frames, expected_client_id="client-1")


def test_position_then_products_and_multiple_products_same_image():
    rows = reconcile(
        [
            frame(1, detections=[detection()]),
            frame(2, items=["r1", "r2"]),
        ]
    )
    assert [row.assignment_status for row in rows] == [
        AssignmentStatus.ASSIGNED_AUTOMATIC,
        AssignmentStatus.ASSIGNED_AUTOMATIC,
    ]
    assert {row.position_label_id for row in rows} == {"label-1"}


def test_position_change():
    rows = reconcile(
        [
            frame(1, items=["r1"], detections=[detection(label_id="left")]),
            frame(
                2,
                items=["r2"],
                detections=[detection(detection_id="d2", label_id="right")],
            ),
        ]
    )
    assert [row.position_label_id for row in rows] == ["left", "right"]


def test_product_before_first_position():
    row = reconcile([frame(1, items=["r1"])])[0]
    assert row.assignment_status is AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION


def test_same_image_detection_applies_before_items():
    row = reconcile([frame(1, items=["r1"], detections=[detection()])])[0]
    assert row.assignment_status is AssignmentStatus.ASSIGNED_AUTOMATIC


def test_ambiguity_clears_until_next_valid_position():
    rows = reconcile(
        [
            frame(1, detections=[detection()]),
            frame(2, items=["r1"], detections=[detection("AMBIGUOUS_POSITION_DETECTION")]),
            frame(3, items=["r2"]),
            frame(4, items=["r3"], detections=[detection(detection_id="d2")]),
        ]
    )
    assert [row.assignment_status for row in rows] == [
        AssignmentStatus.UNASSIGNED_AFTER_AMBIGUOUS_POSITION,
        AssignmentStatus.UNASSIGNED_AFTER_AMBIGUOUS_POSITION,
        AssignmentStatus.ASSIGNED_AUTOMATIC,
    ]


@pytest.mark.parametrize(
    ("status", "signature", "client_id"),
    [
        ("INVALID_SIGNATURE", "INVALID", "client-1"),
        ("VALID", "VALID", "other-client"),
        ("LABEL_INVALIDATED", "VALID", "client-1"),
    ],
)
def test_clear_policies(status, signature, client_id):
    rows = reconcile(
        [
            frame(1, detections=[detection()]),
            frame(
                2,
                items=["r1"],
                detections=[detection(status, signature=signature, client_id=client_id)],
            ),
        ]
    )
    assert rows[0].assignment_status is AssignmentStatus.UNASSIGNED_INVALID_POSITION
    row = reconcile(
        [
            frame(1, detections=[detection()]),
            frame(3, items=["r1"]),
        ]
    )[0]
    assert row.position_label_id == "label-1"
    assert row.warnings == ("SEQUENCE_GAP",)


def test_unordered_asset_is_excluded():
    row = reconcile([frame(None, asset="unordered", items=["r1"])])[0]
    assert row.assignment_status is AssignmentStatus.UNASSIGNED_UNORDERED_ASSET


def test_two_sessions_raise():
    with pytest.raises(PositionReconciliationSessionMismatchError):
        reconcile([frame(1, session="one"), frame(2, session="two")])


def test_duplicate_sequence_for_different_assets_raises():
    with pytest.raises(PositionReconciliationSequenceInvalidError):
        reconcile([frame(1, asset="asset-a"), frame(1, asset="asset-b")])


def test_decisions_are_deterministic():
    frames = [
        frame(2, asset="b", items=["r2"]),
        frame(1, asset="a", items=["r1"], detections=[detection()]),
    ]
    assert reconcile(frames) == reconcile(list(reversed(frames)))
