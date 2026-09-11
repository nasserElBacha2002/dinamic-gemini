"""Pure sequential last-valid-position reconciler."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.errors import (
    PositionReconciliationSequenceInvalidError,
    PositionReconciliationSessionMismatchError,
)
from src.application.services.position_reconciliation.position_policy import (
    evaluate_position_establishment,
)
from src.domain.position_reconciliation.entities import (
    AssignmentSource,
    AssignmentStatus,
    OrderedImageFrame,
    PositionAssignmentDecision,
    PositionDetectionRef,
    PositionTransitionAction,
)


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
        current_unsigned_warning: tuple[str, ...] = ()

        for frame in ordered:
            sequence = int(frame.sequence_number or 0)
            gap_warning: tuple[str, ...] = ()
            if previous_sequence is not None and sequence > previous_sequence + 1:
                gap_warning = ("SEQUENCE_GAP",)
            if previous_sequence is None or sequence > previous_sequence:
                previous_sequence = sequence

            for detection in frame.position_detections:
                establishment = evaluate_position_establishment(
                    detection, expected_client_id=expected_client_id
                )
                action = establishment.action
                status = establishment.reason

                if action is PositionTransitionAction.SET_POSITION:
                    current = detection
                    cleared_by_ambiguous = False
                    cleared_by_invalid = False
                    if status == "LEGACY_UNSIGNED_REQUIRES_REVIEW":
                        current_unsigned_warning = ("LEGACY_UNSIGNED_REQUIRES_REVIEW",)
                    else:
                        current_unsigned_warning = ()
                elif action is PositionTransitionAction.CLEAR_POSITION:
                    current = None
                    current_unsigned_warning = ()
                    if status == "AMBIGUOUS_POSITION_DETECTION":
                        cleared_by_ambiguous = True
                        cleared_by_invalid = False
                    else:
                        cleared_by_invalid = True
                        cleared_by_ambiguous = False

            item_warnings = gap_warning + current_unsigned_warning
            for item in sorted(frame.item_results, key=lambda ref: ref.result_id):
                decisions.append(
                    self._decision(
                        frame=frame,
                        result_id=item.result_id,
                        current=current,
                        cleared_by_ambiguous=cleared_by_ambiguous,
                        cleared_by_invalid=cleared_by_invalid,
                        warnings=item_warnings,
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
                aisle_location_id=current.aisle_location_id,
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
