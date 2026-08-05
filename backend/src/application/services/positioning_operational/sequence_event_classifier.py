"""Typed classification of positioning sequence events (P1 semantics).

Detection status ≠ label resolved ≠ transition applied.
``position_label_name`` is never treated as identity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
)


class PositionSequenceEventKind(str, Enum):
    NO_POSITION_SYMBOL = "NO_POSITION_SYMBOL"
    POSITION_LABEL_UNRESOLVED = "POSITION_LABEL_UNRESOLVED"
    POSITION_LABEL_RESOLVED = "POSITION_LABEL_RESOLVED"
    POSITION_TRANSITION_APPLIED = "POSITION_TRANSITION_APPLIED"


class PositionSequenceReasonCode(str, Enum):
    NONE = "NONE"
    MISSING_POSITION_ID = "MISSING_POSITION_ID"
    AMBIGUOUS_DISTINCT_LABELS = "AMBIGUOUS_DISTINCT_LABELS"
    LABEL_RESOLVED = "LABEL_RESOLVED"
    TRANSITION_APPLIED = "TRANSITION_APPLIED"
    NO_SYMBOL = "NO_SYMBOL"
    UNKNOWN_STATUS = "UNKNOWN_STATUS"


_RESOLVED_CLASS_STATUSES = frozenset(
    {
        PositionLabelDetectionStatus.VALID.value,
        PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW.value,
    }
)

_NO_SYMBOL_STATUSES = frozenset(
    {
        PositionLabelDetectionStatus.NO_LABEL.value,
        PositionLabelDetectionStatus.FEATURE_DISABLED.value,
    }
)

_KNOWN_STATUSES = frozenset(s.value for s in PositionLabelDetectionStatus)


@dataclass(frozen=True)
class SequencePositionEvent:
    """Result of classifying detections for one source asset."""

    event_kind: PositionSequenceEventKind
    detection_status: str | None
    position_label_id: str | None
    position_label_name: str | None
    reason_code: PositionSequenceReasonCode
    message: str | None


def normalize_detection_status(
    status: str | PositionLabelDetectionStatus | None,
) -> str:
    if status is None:
        return ""
    if isinstance(status, PositionLabelDetectionStatus):
        return status.value
    return str(status).strip().upper()


def is_resolved_position_detection(
    detection: ImagePositionLabelDetection,
) -> bool:
    """True when the row can establish a position cursor (status + id)."""
    status = normalize_detection_status(detection.detection_status)
    label_id = (detection.position_label_id or "").strip()
    return status in _RESOLVED_CLASS_STATUSES and bool(label_id)


def is_resolved_position_detection_status(
    status: str | PositionLabelDetectionStatus | None,
    *,
    position_label_id: str | None = None,
) -> bool:
    """Status-only helper; requires ``position_label_id`` for a true resolved count."""
    normalized = normalize_detection_status(status)
    if normalized not in _RESOLVED_CLASS_STATUSES:
        return False
    return bool((position_label_id or "").strip())


def message_for_sequence_event(event: SequencePositionEvent) -> str | None:
    kind = event.event_kind
    status = event.detection_status or ""
    reason = event.reason_code

    if kind is PositionSequenceEventKind.NO_POSITION_SYMBOL:
        return None
    if kind is PositionSequenceEventKind.POSITION_TRANSITION_APPLIED:
        if status == PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW.value:
            return (
                "Evento de transición de posición. "
                "Etiqueta sin firma criptográfica: queda marcada para revisión."
            )
        return "Evento de transición de posición"
    if kind is PositionSequenceEventKind.POSITION_LABEL_RESOLVED:
        if status == PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW.value:
            return (
                "Etiqueta de posicionamiento resuelta. "
                "Etiqueta sin firma criptográfica: queda marcada para revisión."
            )
        return "Etiqueta de posicionamiento resuelta"
    # UNRESOLVED
    if reason is PositionSequenceReasonCode.UNKNOWN_STATUS and status:
        motive = status
    elif reason is not PositionSequenceReasonCode.NONE:
        motive = reason.value
    else:
        motive = status or "UNKNOWN"
    return f"Etiqueta de posicionamiento detectada, pero no resuelta. Motivo: {motive}"


def reduce_asset_detections(
    detections: Sequence[ImagePositionLabelDetection],
    *,
    reconciler_transition_applied: bool = False,
) -> SequencePositionEvent:
    """Deterministic reduction of all detections for one asset.

    Independent of repository order. ``reconciler_transition_applied`` must be
    true only when concrete SET_POSITION evidence exists; otherwise a resolved
    label yields ``POSITION_LABEL_RESOLVED`` (not transition applied).

    Gap: P1 has no persisted per-frame transition ledger; callers should leave
    ``reconciler_transition_applied=False`` until that evidence exists.
    """
    rows = list(detections)
    if not rows:
        return SequencePositionEvent(
            event_kind=PositionSequenceEventKind.NO_POSITION_SYMBOL,
            detection_status=None,
            position_label_id=None,
            position_label_name=None,
            reason_code=PositionSequenceReasonCode.NO_SYMBOL,
            message=None,
        )

    # Stable order for tie-breaks (never depend on list order from repo).
    ordered = sorted(
        rows,
        key=lambda d: (
            normalize_detection_status(d.detection_status),
            (d.position_label_id or ""),
            d.id,
        ),
    )

    resolved_ok: list[ImagePositionLabelDetection] = []
    resolved_missing_id: list[ImagePositionLabelDetection] = []
    ambiguous_rows: list[ImagePositionLabelDetection] = []
    unresolved_rows: list[ImagePositionLabelDetection] = []
    no_symbol_rows: list[ImagePositionLabelDetection] = []

    for det in ordered:
        status = normalize_detection_status(det.detection_status)
        label_id = (det.position_label_id or "").strip() or None
        if status in _NO_SYMBOL_STATUSES:
            no_symbol_rows.append(det)
            continue
        if status == PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION.value:
            ambiguous_rows.append(det)
            continue
        if status in _RESOLVED_CLASS_STATUSES:
            if label_id:
                resolved_ok.append(det)
            else:
                resolved_missing_id.append(det)
            continue
        unresolved_rows.append(det)

    if ambiguous_rows and not resolved_ok:
        primary = ambiguous_rows[0]
        return _unresolved_event(
            primary,
            reason=PositionSequenceReasonCode.AMBIGUOUS_DISTINCT_LABELS,
            status_override=PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION.value,
        )

    if resolved_ok:
        distinct_ids = {
            (d.position_label_id or "").strip()
            for d in resolved_ok
            if (d.position_label_id or "").strip()
        }
        if len(distinct_ids) > 1:
            primary = resolved_ok[0]
            return _unresolved_event(
                primary,
                reason=PositionSequenceReasonCode.AMBIGUOUS_DISTINCT_LABELS,
                status_override=PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION.value,
            )
        # Prefer VALID over LEGACY when both share the same id.
        preferred = sorted(
            resolved_ok,
            key=lambda d: (
                (
                    0
                    if normalize_detection_status(d.detection_status)
                    == PositionLabelDetectionStatus.VALID.value
                    else 1
                ),
                d.id,
            ),
        )[0]
        # Ambiguous row alongside a single valid id still wins as ambiguous.
        if ambiguous_rows:
            return _unresolved_event(
                preferred,
                reason=PositionSequenceReasonCode.AMBIGUOUS_DISTINCT_LABELS,
                status_override=PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION.value,
            )
        status = normalize_detection_status(preferred.detection_status)
        label_id = (preferred.position_label_id or "").strip() or None
        name = (preferred.position_name_snapshot or "").strip() or None
        if reconciler_transition_applied:
            kind = PositionSequenceEventKind.POSITION_TRANSITION_APPLIED
            reason = PositionSequenceReasonCode.TRANSITION_APPLIED
        else:
            kind = PositionSequenceEventKind.POSITION_LABEL_RESOLVED
            reason = PositionSequenceReasonCode.LABEL_RESOLVED
        event = SequencePositionEvent(
            event_kind=kind,
            detection_status=status,
            position_label_id=label_id,
            position_label_name=name,
            reason_code=reason,
            message=None,
        )
        return SequencePositionEvent(
            event_kind=event.event_kind,
            detection_status=event.detection_status,
            position_label_id=event.position_label_id,
            position_label_name=event.position_label_name,
            reason_code=event.reason_code,
            message=message_for_sequence_event(event),
        )

    if resolved_missing_id:
        return _unresolved_event(
            resolved_missing_id[0],
            reason=PositionSequenceReasonCode.MISSING_POSITION_ID,
        )

    if ambiguous_rows:
        return _unresolved_event(
            ambiguous_rows[0],
            reason=PositionSequenceReasonCode.AMBIGUOUS_DISTINCT_LABELS,
            status_override=PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION.value,
        )

    if unresolved_rows:
        primary = unresolved_rows[0]
        status = normalize_detection_status(primary.detection_status)
        reason = (
            PositionSequenceReasonCode.UNKNOWN_STATUS
            if status not in _KNOWN_STATUSES
            else PositionSequenceReasonCode.NONE
        )
        event = SequencePositionEvent(
            event_kind=PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED,
            detection_status=status or None,
            position_label_id=(primary.position_label_id or "").strip() or None,
            position_label_name=(primary.position_name_snapshot or "").strip() or None,
            reason_code=reason,
            message=None,
        )
        return SequencePositionEvent(
            event_kind=event.event_kind,
            detection_status=event.detection_status,
            position_label_id=event.position_label_id,
            position_label_name=event.position_label_name,
            reason_code=event.reason_code,
            message=message_for_sequence_event(event),
        )

    # Only NO_LABEL / FEATURE_DISABLED
    primary = no_symbol_rows[0]
    status = normalize_detection_status(primary.detection_status)
    return SequencePositionEvent(
        event_kind=PositionSequenceEventKind.NO_POSITION_SYMBOL,
        detection_status=status or None,
        position_label_id=None,
        position_label_name=None,
        reason_code=PositionSequenceReasonCode.NO_SYMBOL,
        message=None,
    )


def _unresolved_event(
    detection: ImagePositionLabelDetection,
    *,
    reason: PositionSequenceReasonCode,
    status_override: str | None = None,
) -> SequencePositionEvent:
    status = status_override or normalize_detection_status(detection.detection_status)
    event = SequencePositionEvent(
        event_kind=PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED,
        detection_status=status or None,
        position_label_id=(detection.position_label_id or "").strip() or None,
        position_label_name=(detection.position_name_snapshot or "").strip() or None,
        reason_code=reason,
        message=None,
    )
    return SequencePositionEvent(
        event_kind=event.event_kind,
        detection_status=event.detection_status,
        position_label_id=event.position_label_id,
        position_label_name=event.position_label_name,
        reason_code=event.reason_code,
        message=message_for_sequence_event(event),
    )
