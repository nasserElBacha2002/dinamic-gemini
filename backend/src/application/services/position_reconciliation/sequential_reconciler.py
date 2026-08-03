"""Pure sequential last-valid-position reconciler."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from src.application.errors import (
    PositionReconciliationSequenceInvalidError,
    PositionReconciliationSessionMismatchError,
)
from src.application.services.position_reconciliation.transitions import (
    resolve_position_transition,
)
from src.domain.position_reconciliation.entities import (
    AssignmentSource,
    AssignmentStatus,
    OrderedImageFrame,
    PositionAssignmentDecision,
    PositionDetectionRef,
    PositionTransitionAction,
)


def _value(value: str | Enum) -> str:
    raw = value.value if isinstance(value, Enum) else value
    return str(raw).strip().upper()


class SequentialPositionReconciler:
    """Associate each item with the position state at its ordered image."""

    def reconcile(
        self,
        frames: Sequence[OrderedImageFrame],
        *,
        expected_client_id: str,
    ) -> list[PositionAssignmentDecision]:
        sessions = {
            frame.ordered_capture_session_id for frame in frames if frame.ordered_capture_session_id
        }
        if len(sessions) > 1:
            raise PositionReconciliationSessionMismatchError(
                "Job assets belong to multiple ordered capture sessions"
            )

        source_by_sequence: dict[int, str] = {}
        for frame in frames:
            if frame.sequence_number is None:
                continue
            sequence = int(frame.sequence_number)
            existing = source_by_sequence.setdefault(sequence, frame.source_asset_id)
            if existing != frame.source_asset_id:
                raise PositionReconciliationSequenceInvalidError(
                    f"Sequence {sequence} maps to multiple source assets: "
                    f"{existing}, {frame.source_asset_id}"
                )

        ordered = sorted(
            (frame for frame in frames if frame.sequence_number is not None),
            key=lambda frame: (
                int(frame.sequence_number or 0),
                frame.client_image_id or frame.source_asset_id,
                frame.source_asset_id,
            ),
        )
        unordered = sorted(
            (frame for frame in frames if frame.sequence_number is None),
            key=lambda frame: (
                frame.client_image_id or frame.source_asset_id,
                frame.source_asset_id,
            ),
        )

        decisions: list[PositionAssignmentDecision] = []
        current: PositionDetectionRef | None = None
        cleared_by_ambiguous = False
        cleared_by_invalid = False
        previous_sequence: int | None = None

        for frame in ordered:
            sequence = int(frame.sequence_number or 0)
            gap_warning: tuple[str, ...] = ()
            if previous_sequence is not None and sequence > previous_sequence + 1:
                gap_warning = ("SEQUENCE_GAP",)
            if previous_sequence is None or sequence > previous_sequence:
                previous_sequence = sequence

            for detection in frame.position_detections:
                status = _value(detection.detection_status)
                action = resolve_position_transition(detection.detection_status)
                signature = _value(detection.signature_status)

                if status == "VALID":
                    if detection.client_id != expected_client_id:
                        action = PositionTransitionAction.CLEAR_POSITION
                        status = "CLIENT_MISMATCH"
                    elif signature == "INVALID":
                        action = PositionTransitionAction.CLEAR_POSITION
                        status = "INVALID_SIGNATURE"
                    elif signature != "VALID" or not detection.position_label_id:
                        action = PositionTransitionAction.KEEP_POSITION

                if action is PositionTransitionAction.SET_POSITION:
                    current = detection
                    cleared_by_ambiguous = False
                    cleared_by_invalid = False
                elif action is PositionTransitionAction.CLEAR_POSITION:
                    current = None
                    if status == "AMBIGUOUS_POSITION_DETECTION":
                        cleared_by_ambiguous = True
                        cleared_by_invalid = False
                    else:
                        cleared_by_invalid = True
                        cleared_by_ambiguous = False

            for item in sorted(frame.item_results, key=lambda ref: ref.result_id):
                decisions.append(
                    self._decision(
                        frame=frame,
                        result_id=item.result_id,
                        current=current,
                        cleared_by_ambiguous=cleared_by_ambiguous,
                        cleared_by_invalid=cleared_by_invalid,
                        warnings=gap_warning,
                    )
                )

        for frame in unordered:
            for item in sorted(frame.item_results, key=lambda ref: ref.result_id):
                decisions.append(
                    PositionAssignmentDecision(
                        result_id=item.result_id,
                        source_asset_id=frame.source_asset_id,
                        ordered_capture_session_id=frame.ordered_capture_session_id,
                        sequence_number=None,
                        assignment_status=AssignmentStatus.UNASSIGNED_UNORDERED_ASSET,
                        assignment_reason="UNORDERED_ASSET",
                    )
                )
        return decisions

    @staticmethod
    def _decision(
        *,
        frame: OrderedImageFrame,
        result_id: str,
        current: PositionDetectionRef | None,
        cleared_by_ambiguous: bool,
        cleared_by_invalid: bool,
        warnings: tuple[str, ...],
    ) -> PositionAssignmentDecision:
        if current is not None:
            return PositionAssignmentDecision(
                result_id=result_id,
                source_asset_id=frame.source_asset_id,
                ordered_capture_session_id=frame.ordered_capture_session_id,
                sequence_number=frame.sequence_number,
                position_label_id=current.position_label_id,
                position_name_snapshot=current.position_name_snapshot,
                source_detection_id=current.id,
                assignment_status=AssignmentStatus.ASSIGNED_AUTOMATIC,
                assignment_reason="LAST_VALID_POSITION",
                assignment_source=AssignmentSource.AUTOMATIC,
                warnings=warnings,
            )
        if cleared_by_ambiguous:
            status = AssignmentStatus.UNASSIGNED_AFTER_AMBIGUOUS_POSITION
        elif cleared_by_invalid:
            status = AssignmentStatus.UNASSIGNED_INVALID_POSITION
        else:
            status = AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION
        return PositionAssignmentDecision(
            result_id=result_id,
            source_asset_id=frame.source_asset_id,
            ordered_capture_session_id=frame.ordered_capture_session_id,
            sequence_number=frame.sequence_number,
            assignment_status=status,
            assignment_reason=status.value,
            warnings=warnings,
        )
