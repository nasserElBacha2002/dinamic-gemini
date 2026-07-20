"""Update aisle (code and/or identification mode override)."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import DuplicateAisleCodeError
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.legacy_processing_guard import (
    reject_legacy_mode_for_new_configuration,
)
from src.application.services.optional_unset import UNSET, OptionalModeUpdate, UnsetType
from src.domain.aisle.entities import Aisle
from src.domain.aisle_identification.modes import AisleIdentificationMode, parse_identification_mode

_MAX_AISLE_CODE_LEN = 64


@dataclass
class UpdateAisleCommand:
    inventory_id: str
    aisle_id: str
    code: str | None = None
    identification_mode: OptionalModeUpdate = UNSET


UpdateAisleCodeCommand = UpdateAisleCommand


class UpdateAisleUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        clock: Clock,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._clock = clock

    def execute(self, command: UpdateAisleCommand) -> Aisle:
        if command.code is None and isinstance(command.identification_mode, UnsetType):
            raise ValueError("At least one field must be provided")

        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )

        changed = False
        if command.code is not None:
            code = command.code.strip()
            if not code:
                raise ValueError("Aisle code must not be empty")
            if len(code) > _MAX_AISLE_CODE_LEN:
                raise ValueError(f"Aisle code must be at most {_MAX_AISLE_CODE_LEN} characters")
            if aisle.code != code:
                existing = self._aisle_repo.get_by_inventory_and_code(command.inventory_id, code)
                if existing is not None and existing.id != aisle.id:
                    raise DuplicateAisleCodeError(
                        f"An aisle with code {code!r} already exists in this inventory"
                    )
                aisle.code = code
                changed = True

        if not isinstance(command.identification_mode, UnsetType):
            mode: AisleIdentificationMode | None
            if command.identification_mode is None:
                mode = None
            elif isinstance(command.identification_mode, AisleIdentificationMode):
                mode = command.identification_mode
            else:
                mode = parse_identification_mode(command.identification_mode)
            reject_legacy_mode_for_new_configuration(mode, context="aisle")
            if aisle.identification_mode != mode:
                aisle.identification_mode = mode
                changed = True

        if not changed:
            return aisle

        aisle.updated_at = self._clock.now()
        self._aisle_repo.save(aisle)
        return aisle


UpdateAisleCodeUseCase = UpdateAisleUseCase
