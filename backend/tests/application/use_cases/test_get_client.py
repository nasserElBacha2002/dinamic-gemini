"""Tests for GetClientUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import ClientNotFoundError
from src.application.ports.repositories import ClientRepository
from src.application.use_cases.clients.get_client import GetClientUseCase
from src.domain.client.entities import Client, ClientStatus


class StubClientRepo(ClientRepository):
    def __init__(self) -> None:
        self._store: dict[str, Client] = {}

    def save(self, client: Client) -> None:
        self._store[client.id] = client

    def get_by_id(self, client_id: str) -> Client | None:
        return self._store.get(client_id)

    def list_all(self):
        return list(self._store.values())


def test_get_client_returns_entity_when_found() -> None:
    repo = StubClientRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client = Client(
        id="client-1",
        name="Retail A",
        status=ClientStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    repo.save(client)
    use_case = GetClientUseCase(client_repo=repo)

    result = use_case.execute("client-1")

    assert result.id == "client-1"
    assert result.name == "Retail A"


def test_get_client_raises_when_not_found() -> None:
    repo = StubClientRepo()
    use_case = GetClientUseCase(client_repo=repo)

    with pytest.raises(ClientNotFoundError):
        use_case.execute("missing")

