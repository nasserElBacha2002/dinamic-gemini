"""GetClient use case — Phase A1 foundation."""

from __future__ import annotations

from src.application.errors import ClientNotFoundError
from src.application.ports.repositories import ClientRepository
from src.domain.client.entities import Client


class GetClientUseCase:
    def __init__(self, client_repo: ClientRepository) -> None:
        self._client_repo = client_repo

    def execute(self, client_id: str) -> Client:
        client = self._client_repo.get_by_id(client_id)
        if client is None:
            raise ClientNotFoundError(f"Client not found: {client_id}")
        return client

