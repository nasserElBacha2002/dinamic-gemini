"""In-memory implementation of ClientRepository — Phase A1 foundation."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import ClientRepository
from src.domain.client.entities import Client


class MemoryClientRepository(ClientRepository):
    def __init__(self) -> None:
        self._store: dict[str, Client] = {}

    def save(self, client: Client) -> None:
        self._store[client.id] = client

    def get_by_id(self, client_id: str) -> Client | None:
        return self._store.get(client_id)

    def list_all(self) -> Sequence[Client]:
        return sorted(self._store.values(), key=lambda c: c.created_at, reverse=True)

