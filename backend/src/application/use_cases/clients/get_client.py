"""GetClient use case — tenant-scoped (Stage 2)."""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.repositories import ClientRepository
from src.application.services.client_access_policy import ClientAccessPolicy
from src.domain.client.entities import Client


class GetClientUseCase:
    def __init__(self, client_repo: ClientRepository) -> None:
        self._policy = ClientAccessPolicy(client_repo)

    def execute(self, client_id: str, principal: AccessPrincipal) -> Client:
        return self._policy.require_client(client_id, principal)
