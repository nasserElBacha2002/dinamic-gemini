"""Single read model resolving manual overrides over published automatic assignments."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.client_position_label_repository import (
    ClientPositionLabelRepository,
)
from src.application.ports.manual_position_override_repository import (
    ManualPositionOverrideRepository,
)
from src.application.services.position_reconciliation.published_assignment_read_model import (
    PositionReadAvailability,
)
from src.application.services.position_reconciliation.published_assignment_reader import (
    PublishedPositionAssignmentReader,
)
from src.domain.client_position_label.entities import ClientPositionLabelStatus
from src.domain.position_overrides.entities import (
    EffectivePositionSource,
    EffectiveProductPositionView,
    PositionOverrideAction,
    PositionOverridePositionRef,
)


def _automatic_version(value: str | None) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class EffectivePositionReader:
    def __init__(
        self,
        *,
        automatic_reader: PublishedPositionAssignmentReader,
        override_repo: ManualPositionOverrideRepository,
        label_repo: ClientPositionLabelRepository | None = None,
    ) -> None:
        self._automatic_reader = automatic_reader
        self._override_repo = override_repo
        self._label_repo = label_repo

    def load_for_job(
        self,
        job_id: str,
        *,
        result_ids: Sequence[str],
        active_result_ids: set[str] | None = None,
    ) -> dict[str, EffectiveProductPositionView]:
        automatic = self._automatic_reader.load_for_job(job_id, result_ids=result_ids)
        output: dict[str, EffectiveProductPositionView] = {}
        for result_id in result_ids:
            auto = automatic[result_id]
            auto_position = (
                PositionOverridePositionRef(auto.position.id, auto.position.name)
                if auto.position
                else None
            )
            override = self._override_repo.get_active(job_id, result_id)
            warnings: list[str] = []
            if auto.availability is PositionReadAvailability.RECONCILIATION_STALE:
                warnings.append("RECONCILIATION_STALE")
            if override is None:
                source = (
                    EffectivePositionSource.AUTOMATIC
                    if auto_position is not None
                    else EffectivePositionSource.NONE
                )
                status = (
                    "ASSIGNED_AUTOMATIC"
                    if auto_position is not None
                    else (
                        "NO_RECONCILIATION"
                        if auto.availability is PositionReadAvailability.NO_RECONCILIATION
                        else "UNASSIGNED_AUTOMATIC"
                    )
                )
                output[result_id] = EffectiveProductPositionView(
                    result_id=result_id,
                    effective_position=auto_position,
                    effective_source=source,
                    effective_status=status,
                    automatic_position=auto_position,
                    automatic_assignment_status=auto.assignment_status,
                    manual_override=None,
                    reconciliation_status=auto.reconciliation_status,
                    warnings=tuple(warnings),
                    version=_automatic_version(auto.reconciliation_version),
                    automatic_reconciliation_id=auto.reconciliation_id,
                    source_asset_id=auto.source_asset_id,
                )
                continue

            if (
                override.automatic_reconciliation_id
                and auto.reconciliation_id
                and override.automatic_reconciliation_id != auto.reconciliation_id
            ):
                warnings.append("AUTOMATIC_CHANGED_AFTER_OVERRIDE")
            if active_result_ids is not None and result_id not in active_result_ids:
                warnings.append("MANUAL_OVERRIDE_ORPHANED")
            if override.new_position_label_id and self._label_repo is not None:
                label = self._label_repo.get_by_id(override.new_position_label_id)
                if label is None or label.status is not ClientPositionLabelStatus.ACTIVE:
                    warnings.append("MANUAL_POSITION_INVALIDATED")

            removed = override.override_action is PositionOverrideAction.REMOVE_POSITION
            effective_position = (
                None
                if removed
                else PositionOverridePositionRef(
                    override.new_position_label_id,
                    override.new_position_name_snapshot,
                )
            )
            output[result_id] = EffectiveProductPositionView(
                result_id=result_id,
                effective_position=effective_position,
                effective_source=EffectivePositionSource.MANUAL,
                effective_status="UNASSIGNED_MANUAL" if removed else "ASSIGNED_MANUAL",
                automatic_position=auto_position,
                automatic_assignment_status=auto.assignment_status,
                manual_override=override,
                reconciliation_status=auto.reconciliation_status,
                warnings=tuple(dict.fromkeys(warnings)),
                version=override.version,
                automatic_reconciliation_id=auto.reconciliation_id,
                source_asset_id=auto.source_asset_id,
            )
        return output
