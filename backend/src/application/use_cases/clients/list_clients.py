"""ListClients use case — Phase A1 foundation."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import ClientRepository
from src.domain.client.entities import Client


class ListClientsUseCase:
    def __init__(self, client_repo: ClientRepository) -> None:
        self._client_repo = client_repo

    def execute(self) -> Sequence[Client]:
        return self._client_repo.list_all()

