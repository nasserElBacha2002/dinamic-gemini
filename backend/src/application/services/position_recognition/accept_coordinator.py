"""Accept canonically valid positions and materialize when channel rollout requires it."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.position_materialization import MaterializePositionCommand
from src.application.services.position_materialization.service import MaterializePositionService
from src.application.services.position_recognition.channel_gates import (
    FlexiblePositionChannel,
    FlexiblePositionChannelSettings,
    is_flexible_channel_enabled,
)
from src.domain.position_materialization.entities import (
    MaterializePositionResult,
    PositionMaterializationStatus,
)
from src.domain.position_recognition import (
    CanonicalPositionValidationResult,
    CanonicalPositionValidationStatus,
)


@dataclass(frozen=True)
class AcceptPositionRequest:
    validation: CanonicalPositionValidationResult
    channel: FlexiblePositionChannel
    materialize_command: MaterializePositionCommand | None = None


@dataclass(frozen=True)
class AcceptPositionOutcome:
    accepted: bool
    validation: CanonicalPositionValidationResult
    location_id: str | None
    materialization: MaterializePositionResult | None = None
    error_code: str | None = None

    @property
    def requires_location(self) -> bool:
        return self.accepted and self.location_id is not None


class AcceptPositionCoordinator:
    """Thin accept gate: VALID_UNMATERIALIZED + flexible channel + auto → materialize."""

    def __init__(
        self,
        *,
        settings: FlexiblePositionChannelSettings,
        auto_materialization_enabled: bool,
        materializer: MaterializePositionService | None = None,
    ) -> None:
        self._settings = settings
        self._auto_materialization_enabled = bool(auto_materialization_enabled)
        self._materializer = materializer

    def accept(self, request: AcceptPositionRequest) -> AcceptPositionOutcome:
        validation = request.validation
        if not validation.operationally_accepted:
            return AcceptPositionOutcome(
                accepted=False,
                validation=validation,
                location_id=None,
                error_code=validation.error_code or validation.status.value,
            )

        if validation.status is CanonicalPositionValidationStatus.VALID_EXISTING:
            return AcceptPositionOutcome(
                accepted=True,
                validation=validation,
                location_id=validation.existing_position_label_id,
            )

        if validation.status is not CanonicalPositionValidationStatus.VALID_UNMATERIALIZED:
            return AcceptPositionOutcome(
                accepted=False,
                validation=validation,
                location_id=None,
                error_code=validation.error_code or validation.status.value,
            )

        channel_flexible = is_flexible_channel_enabled(self._settings, request.channel)
        if channel_flexible:
            if not self._auto_materialization_enabled:
                return AcceptPositionOutcome(
                    accepted=False,
                    validation=validation,
                    location_id=None,
                    error_code="AUTO_MATERIALIZATION_REQUIRED_FOR_FLEXIBLE_CHANNEL",
                )
            return self._materialize_required(request)

        # Legacy / non-channel path: VALID_UNMATERIALIZED without channel rollout
        # remains unmaterialized (preexistence policy should usually prevent this).
        return AcceptPositionOutcome(
            accepted=True,
            validation=validation,
            location_id=None,
        )

    def _materialize_required(self, request: AcceptPositionRequest) -> AcceptPositionOutcome:
        validation = request.validation
        if self._materializer is None:
            return AcceptPositionOutcome(
                accepted=False,
                validation=validation,
                location_id=None,
                error_code="POSITION_MATERIALIZER_UNAVAILABLE",
            )
        if request.materialize_command is None:
            return AcceptPositionOutcome(
                accepted=False,
                validation=validation,
                location_id=None,
                error_code="POSITION_MATERIALIZE_COMMAND_REQUIRED",
            )
        result = self._materializer.execute(request.materialize_command)
        if result.status not in {
            PositionMaterializationStatus.MATERIALIZED,
            PositionMaterializationStatus.REUSED,
        }:
            return AcceptPositionOutcome(
                accepted=False,
                validation=validation,
                location_id=None,
                materialization=result,
                error_code=result.error_code or result.status.value,
            )
        location_id = (result.location_id or "").strip() or None
        if location_id is None:
            # Soft-accept with null location is forbidden when productive position required.
            return AcceptPositionOutcome(
                accepted=False,
                validation=validation,
                location_id=None,
                materialization=result,
                error_code="POSITION_LOCATION_ID_REQUIRED",
            )
        return AcceptPositionOutcome(
            accepted=True,
            validation=validation,
            location_id=location_id,
            materialization=result,
        )
