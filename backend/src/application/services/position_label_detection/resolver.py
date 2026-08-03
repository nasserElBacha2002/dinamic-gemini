"""Resolve client-scoped position labels after signature validation (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.client_position_label_repository import ClientPositionLabelRepository
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelStatus,
)
from src.domain.position_label_detection.entities import PositionLabelDetectionStatus


@dataclass(frozen=True)
class PositionLabelResolveResult:
    detection_status: PositionLabelDetectionStatus
    label: ClientPositionLabel | None = None
    detail: str | None = None


class PositionLabelResolver:
    def __init__(self, *, label_repo: ClientPositionLabelRepository) -> None:
        self._labels = label_repo

    def resolve(
        self,
        *,
        public_label_id: str,
        expected_client_id: str,
    ) -> PositionLabelResolveResult:
        label = self._labels.get_by_public_identifier(public_label_id)
        if label is None:
            return PositionLabelResolveResult(
                detection_status=PositionLabelDetectionStatus.LABEL_NOT_FOUND,
                detail="label_id not found",
            )
        if (label.client_id or "").strip() != (expected_client_id or "").strip():
            # Do not leak cross-tenant name / details.
            return PositionLabelResolveResult(
                detection_status=PositionLabelDetectionStatus.CLIENT_MISMATCH,
                detail="position label belongs to another client",
            )
        if label.status is ClientPositionLabelStatus.INVALIDATED:
            return PositionLabelResolveResult(
                detection_status=PositionLabelDetectionStatus.LABEL_INVALIDATED,
                label=label,
                detail="label invalidated",
            )
        if label.status is not ClientPositionLabelStatus.ACTIVE:
            return PositionLabelResolveResult(
                detection_status=PositionLabelDetectionStatus.LABEL_INVALIDATED,
                label=label,
                detail=f"label status={label.status.value}",
            )
        return PositionLabelResolveResult(
            detection_status=PositionLabelDetectionStatus.VALID,
            label=label,
        )
