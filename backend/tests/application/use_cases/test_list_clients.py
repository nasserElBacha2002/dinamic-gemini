"""Tests for ListClientsUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.repositories import ClientRepository
from src.application.use_cases.clients.list_clients import ListClientsUseCase
from src.domain.client.entities import Client, ClientStatus


class StubClientRepo(ClientRepository):
    def __init__(self, clients: list[Client]) -> None:
        self._store = {c.id: c for c in clients}

    def save(self, client: Client) -> None:
        self._store[client.id] = client

    def get_by_id(self, client_id: str) -> Client | None:
        return self._store.get(client_id)

    def list_all(self):
        return list(self._store.values())


def test_list_clients_returns_all() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    c1 = Client("c1", "A", ClientStatus.ACTIVE, now, now)
    c2 = Client("c2", "B", ClientStatus.INACTIVE, now, now)
    repo = StubClientRepo([c1, c2])
    use_case = ListClientsUseCase(client_repo=repo)

    result = use_case.execute()

    assert len(result) == 2
    assert {c.id for c in result} == {"c1", "c2"}

