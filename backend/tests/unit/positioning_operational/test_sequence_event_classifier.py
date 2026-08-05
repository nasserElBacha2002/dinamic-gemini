"""Unit tests for sequence position event classification (P1 semantics)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.positioning_operational.sequence_event_classifier import (
    PositionSequenceEventKind,
    PositionSequenceReasonCode,
    is_resolved_position_detection,
    is_resolved_position_detection_status,
    reduce_asset_detections,
)
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def _det(
    *,
    det_id: str = "d1",
    status: PositionLabelDetectionStatus = PositionLabelDetectionStatus.VALID,
    label_id: str | None = None,
    name: str | None = None,
) -> ImagePositionLabelDetection:
    return ImagePositionLabelDetection(
        id=det_id,
        client_id="c1",
        inventory_id="inv1",
        job_id="job1",
        source_asset_id="asset1",
        detection_status=status,
        signature_status=PositionLabelSignatureStatus.VALID,
        payload_version=1,
        raw_payload_hash=None,
        detector_name="code_scan_shared",
        detector_version="1",
        created_at=NOW,
        updated_at=NOW,
        position_label_id=label_id,
        position_name_snapshot=name,
    )


def test_valid_with_id_and_name_is_label_resolved_not_transition() -> None:
    event = reduce_asset_detections([_det(label_id="L1", name="A")])
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_RESOLVED
    assert event.reason_code is PositionSequenceReasonCode.LABEL_RESOLVED
    assert event.position_label_id == "L1"
    assert event.position_label_name == "A"
    assert event.message == "Etiqueta de posicionamiento resuelta"
    assert "transición" not in (event.message or "").lower()


def test_valid_with_id_without_name_is_resolved() -> None:
    event = reduce_asset_detections([_det(label_id="L1", name=None)])
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_RESOLVED
    assert event.position_label_id == "L1"
    assert event.position_label_name is None


def test_valid_with_name_without_id_is_unresolved_missing_id() -> None:
    event = reduce_asset_detections([_det(label_id=None, name="SoloNombre")])
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert event.reason_code is PositionSequenceReasonCode.MISSING_POSITION_ID
    assert "MISSING_POSITION_ID" in (event.message or "")
    assert "transición" not in (event.message or "").lower()


def test_valid_without_id_is_unresolved_missing_id() -> None:
    event = reduce_asset_detections([_det(label_id=None, name=None)])
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert event.reason_code is PositionSequenceReasonCode.MISSING_POSITION_ID


def test_legacy_with_id_is_resolved() -> None:
    event = reduce_asset_detections(
        [
            _det(
                status=PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW,
                label_id="L1",
                name="A",
            )
        ]
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_RESOLVED
    assert "resuelta" in (event.message or "").lower()
    assert "revisión" in (event.message or "").lower()


def test_legacy_without_id_is_unresolved_missing_id() -> None:
    event = reduce_asset_detections(
        [
            _det(
                status=PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW,
                label_id=None,
                name="A",
            )
        ]
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert event.reason_code is PositionSequenceReasonCode.MISSING_POSITION_ID


def test_no_label_is_no_symbol() -> None:
    event = reduce_asset_detections(
        [_det(status=PositionLabelDetectionStatus.NO_LABEL)]
    )
    assert event.event_kind is PositionSequenceEventKind.NO_POSITION_SYMBOL
    assert event.message is None


def test_feature_disabled_is_no_symbol() -> None:
    event = reduce_asset_detections(
        [_det(status=PositionLabelDetectionStatus.FEATURE_DISABLED)]
    )
    assert event.event_kind is PositionSequenceEventKind.NO_POSITION_SYMBOL
    assert event.message is None


def test_signature_validation_skipped_unresolved() -> None:
    event = reduce_asset_detections(
        [_det(status=PositionLabelDetectionStatus.SIGNATURE_VALIDATION_SKIPPED)]
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert "SIGNATURE_VALIDATION_SKIPPED" in (event.message or "")


def test_label_not_found_unresolved() -> None:
    event = reduce_asset_detections(
        [_det(status=PositionLabelDetectionStatus.LABEL_NOT_FOUND)]
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert "LABEL_NOT_FOUND" in (event.message or "")


def test_invalid_signature_unresolved() -> None:
    event = reduce_asset_detections(
        [_det(status=PositionLabelDetectionStatus.INVALID_SIGNATURE)]
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert "INVALID_SIGNATURE" in (event.message or "")


def test_detection_context_invalid_unresolved() -> None:
    event = reduce_asset_detections(
        [_det(status=PositionLabelDetectionStatus.DETECTION_CONTEXT_INVALID)]
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert "DETECTION_CONTEXT_INVALID" in (event.message or "")


def test_unknown_status_unresolved_neutral_motive() -> None:
    det = _det()
    det.detection_status = "TOTALLY_UNKNOWN_STATUS"  # type: ignore[assignment]
    event = reduce_asset_detections([det])
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert event.reason_code is PositionSequenceReasonCode.UNKNOWN_STATUS
    assert "TOTALLY_UNKNOWN_STATUS" in (event.message or "")
    assert "transición" not in (event.message or "").lower()


def test_two_valid_same_id_consolidates() -> None:
    event = reduce_asset_detections(
        [
            _det(det_id="a", label_id="L1", name="A"),
            _det(det_id="b", label_id="L1", name="A"),
        ]
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_RESOLVED
    assert event.position_label_id == "L1"


def test_two_valid_distinct_ids_ambiguous() -> None:
    event = reduce_asset_detections(
        [
            _det(det_id="a", label_id="L1", name="A"),
            _det(det_id="b", label_id="L2", name="B"),
        ]
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert event.reason_code is PositionSequenceReasonCode.AMBIGUOUS_DISTINCT_LABELS
    assert event.detection_status == "AMBIGUOUS_POSITION_DETECTION"


def test_valid_plus_no_label_both_orders() -> None:
    valid = _det(det_id="v", label_id="L1", name="A")
    none = _det(det_id="n", status=PositionLabelDetectionStatus.NO_LABEL)
    forward = reduce_asset_detections([valid, none])
    reverse = reduce_asset_detections([none, valid])
    assert forward.event_kind is PositionSequenceEventKind.POSITION_LABEL_RESOLVED
    assert reverse.event_kind is PositionSequenceEventKind.POSITION_LABEL_RESOLVED
    assert forward.position_label_id == reverse.position_label_id == "L1"


def test_valid_plus_ambiguous_both_orders() -> None:
    valid = _det(det_id="v", label_id="L1", name="A")
    amb = _det(
        det_id="a",
        status=PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION,
    )
    forward = reduce_asset_detections([valid, amb])
    reverse = reduce_asset_detections([amb, valid])
    assert forward.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert reverse.event_kind is PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED
    assert forward.reason_code is PositionSequenceReasonCode.AMBIGUOUS_DISTINCT_LABELS
    assert reverse.reason_code is PositionSequenceReasonCode.AMBIGUOUS_DISTINCT_LABELS


def test_order_independence_identical_results() -> None:
    rows = [
        _det(det_id="z", status=PositionLabelDetectionStatus.NO_LABEL),
        _det(det_id="a", label_id="L1", name="A"),
        _det(det_id="m", status=PositionLabelDetectionStatus.LABEL_NOT_FOUND),
    ]
    a = reduce_asset_detections(rows)
    b = reduce_asset_detections(list(reversed(rows)))
    assert a == b


def test_label_resolved_without_set_position_evidence() -> None:
    event = reduce_asset_detections(
        [_det(label_id="L1", name="A")],
        reconciler_transition_applied=False,
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_LABEL_RESOLVED
    assert event.event_kind is not PositionSequenceEventKind.POSITION_TRANSITION_APPLIED


def test_transition_applied_only_with_explicit_evidence() -> None:
    event = reduce_asset_detections(
        [_det(label_id="L1", name="A")],
        reconciler_transition_applied=True,
    )
    assert event.event_kind is PositionSequenceEventKind.POSITION_TRANSITION_APPLIED
    assert event.reason_code is PositionSequenceReasonCode.TRANSITION_APPLIED
    assert event.message == "Evento de transición de posición"


def test_is_resolved_requires_id() -> None:
    assert is_resolved_position_detection(_det(label_id="L1")) is True
    assert is_resolved_position_detection(_det(label_id=None, name="A")) is False
    assert is_resolved_position_detection_status("VALID", position_label_id=None) is False
    assert is_resolved_position_detection_status("VALID", position_label_id="L1") is True
    assert is_resolved_position_detection_status("LABEL_NOT_FOUND", position_label_id="L1") is False


def test_empty_detections_no_symbol() -> None:
    event = reduce_asset_detections([])
    assert event.event_kind is PositionSequenceEventKind.NO_POSITION_SYMBOL
    assert event.message is None
