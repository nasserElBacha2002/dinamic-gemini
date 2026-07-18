"""UpdateAisleCode use case — rename aisle display code within an inventory."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import DuplicateAisleCodeError
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.optional_unset import UNSET
from src.domain.aisle.entities import Aisle
from src.domain.aisle_identification.modes import AisleIdentificationMode, parse_identification_mode

_MAX_AISLE_CODE_LEN = 64


@dataclass
class UpdateAisleCodeCommand:
    inventory_id: str
    aisle_id: str
    code: str
    #: UNSET = leave unchanged; None = clear override; mode = set.
    identification_mode: object = UNSET


class UpdateAisleCodeUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        clock: Clock,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._clock = clock

    def execute(self, command: UpdateAisleCodeCommand) -> Aisle:
        code = (command.code or "").strip()
        if not code:
            raise ValueError("Aisle code must not be empty")
        if len(code) > _MAX_AISLE_CODE_LEN:
            raise ValueError(f"Aisle code must be at most {_MAX_AISLE_CODE_LEN} characters")

        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )

        changed = False
        if aisle.code != code:
            existing = self._aisle_repo.get_by_inventory_and_code(command.inventory_id, code)
            if existing is not None and existing.id != aisle.id:
                raise DuplicateAisleCodeError(
                    f"An aisle with code {code!r} already exists in this inventory"
                )
            aisle.code = code
            changed = True

        if command.identification_mode is not UNSET:
            mode = command.identification_mode
            if mode is not None and not isinstance(mode, AisleIdentificationMode):
                mode = parse_identification_mode(str(mode))
            if aisle.identification_mode != mode:
                aisle.identification_mode = mode  # type: ignore[assignment]
                changed = True

        if not changed:
            return aisle

        aisle.updated_at = self._clock.now()
        self._aisle_repo.save(aisle)
        return aisle
