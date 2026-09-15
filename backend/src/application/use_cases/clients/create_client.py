"""CreateClient use case — platform-only (Stage 2)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import InvalidClientNameError
from src.application.ports.clock import Clock
from src.application.ports.repositories import ClientRepository
from src.application.services.client_access_policy import ClientAccessPolicy
from src.domain.client.entities import Client, ClientStatus


@dataclass
class CreateClientCommand:
    name: str
    principal: AccessPrincipal
    status: ClientStatus = ClientStatus.ACTIVE


class CreateClientUseCase:
    def __init__(self, client_repo: ClientRepository, clock: Clock) -> None:
        self._client_repo = client_repo
        self._clock = clock
        self._policy = ClientAccessPolicy(client_repo)

    def execute(self, command: CreateClientCommand) -> Client:
        self._policy.require_platform(command.principal, operation="create_client")
        name = (command.name or "").strip()
        if not name:
            raise InvalidClientNameError("Client name is required")
        now = self._clock.now()
        client = Client(
            id=str(uuid4()),
            name=name,
            status=command.status,
            created_at=now,
            updated_at=now,
        )
        self._client_repo.save(client)
        return client
