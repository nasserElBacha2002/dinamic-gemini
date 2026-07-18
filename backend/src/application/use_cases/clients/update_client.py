"""UpdateClient use case — rename and/or set default identification mode."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import ClientNotFoundError, InvalidClientNameError
from src.application.ports.clock import Clock
from src.application.ports.repositories import ClientRepository
from src.application.services.optional_unset import UNSET, OptionalModeUpdate, UnsetType
from src.domain.aisle_identification.modes import AisleIdentificationMode, parse_identification_mode
from src.domain.client.entities import Client

_MAX_NAME_LEN = 255


@dataclass
class UpdateClientCommand:
    client_id: str
    name: str | None = None
    identification_mode: OptionalModeUpdate = UNSET


class UpdateClientUseCase:
    def __init__(self, client_repo: ClientRepository, clock: Clock) -> None:
        self._client_repo = client_repo
        self._clock = clock

    def execute(self, command: UpdateClientCommand) -> Client:
        if command.name is None and isinstance(command.identification_mode, UnsetType):
            raise ValueError("At least one field must be provided")

        client = self._client_repo.get_by_id(command.client_id)
        if client is None:
            raise ClientNotFoundError(f"Client not found: {command.client_id}")

        changed = False
        if command.name is not None:
            name = command.name.strip()
            if not name:
                raise InvalidClientNameError("Client name must not be empty")
            if len(name) > _MAX_NAME_LEN:
                raise InvalidClientNameError(
                    f"Client name must be at most {_MAX_NAME_LEN} characters"
                )
            if client.name != name:
                client.name = name
                changed = True

        if not isinstance(command.identification_mode, UnsetType):
            mode: AisleIdentificationMode | None
            if command.identification_mode is None:
                mode = None
            elif isinstance(command.identification_mode, AisleIdentificationMode):
                mode = command.identification_mode
            else:
                mode = parse_identification_mode(command.identification_mode)
            if client.default_identification_mode != mode:
                client.default_identification_mode = mode
                changed = True

        if not changed:
            return client

        client.updated_at = self._clock.now()
        self._client_repo.save(client)
        return client
