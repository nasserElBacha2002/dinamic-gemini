"""ListClients use case — tenant-scoped (Stage 2)."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.repositories import ClientRepository
from src.application.services.client_access_policy import ClientAccessPolicy
from src.domain.client.entities import Client


class ListClientsUseCase:
    def __init__(self, client_repo: ClientRepository) -> None:
        self._client_repo = client_repo
        self._policy = ClientAccessPolicy(client_repo)

    def execute(self, principal: AccessPrincipal) -> Sequence[Client]:
        return self._policy.list_visible(principal)
