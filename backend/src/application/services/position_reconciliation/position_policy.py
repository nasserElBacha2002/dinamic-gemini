"""Authoritative fail-closed policy for establishing sequential position state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.application.services.position_reconciliation.transitions import (
    resolve_position_transition,
)
from src.domain.position_reconciliation.entities import (
    PositionDetectionRef,
    PositionTransitionAction,
)


def _value(value: str | Enum) -> str:
    raw = value.value if isinstance(value, Enum) else value
    return str(raw).strip().upper()


@dataclass(frozen=True)
class PositionEstablishment:
    action: PositionTransitionAction
    reason: str


def evaluate_position_establishment(
    detection: PositionDetectionRef,
    *,
    expected_client_id: str,
) -> PositionEstablishment:
    status = _value(detection.detection_status)
    signature = _value(detection.signature_status)
    action = resolve_position_transition(detection.detection_status)

    if status not in {"VALID", "LEGACY_UNSIGNED_REQUIRES_REVIEW"}:
        return PositionEstablishment(action, status)
    if detection.client_id != expected_client_id:
        return PositionEstablishment(PositionTransitionAction.CLEAR_POSITION, "CLIENT_MISMATCH")
    if signature == "INVALID":
        return PositionEstablishment(PositionTransitionAction.CLEAR_POSITION, "INVALID_SIGNATURE")
    if status == "LEGACY_UNSIGNED_REQUIRES_REVIEW":
        action = (
            PositionTransitionAction.SET_POSITION
            if detection.position_label_id
            else PositionTransitionAction.KEEP_POSITION
        )
        return PositionEstablishment(action, status)
    # VALID + catalog label: establish position for signed, flexible-unsigned (MISSING),
    # and signature-skipped supplier paths. INVALID already cleared above.
    if detection.position_label_id and signature in {"VALID", "MISSING", "SKIPPED"}:
        return PositionEstablishment(PositionTransitionAction.SET_POSITION, status)
    if (
        detection.aisle_location_id
        and signature == "SKIPPED"
        and (detection.position_name_snapshot or "").strip()
    ):
        return PositionEstablishment(PositionTransitionAction.SET_POSITION, status)
    return PositionEstablishment(PositionTransitionAction.KEEP_POSITION, status)


def can_establish_position(
    detection: PositionDetectionRef,
    *,
    expected_client_id: str,
) -> bool:
    return (
        evaluate_position_establishment(
            detection, expected_client_id=expected_client_id
        ).action
        is PositionTransitionAction.SET_POSITION
    )
