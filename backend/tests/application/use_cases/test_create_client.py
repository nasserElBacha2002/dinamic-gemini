"""Tests for CreateClientUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import InvalidClientNameError
from src.application.ports.repositories import ClientRepository
from src.application.use_cases.create_client import CreateClientCommand, CreateClientUseCase
from src.domain.client.entities import Client, ClientStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubClientRepo(ClientRepository):
    def __init__(self) -> None:
        self._store: dict[str, Client] = {}

    def save(self, client: Client) -> None:
        self._store[client.id] = client

    def get_by_id(self, client_id: str) -> Client | None:
        return self._store.get(client_id)

    def list_all(self):
        return list(self._store.values())


def test_create_client_success() -> None:
    repo = StubClientRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    use_case = CreateClientUseCase(client_repo=repo, clock=FixedClock(now))

    result = use_case.execute(CreateClientCommand(name="Retail A"))

    assert result.name == "Retail A"
    assert result.status == ClientStatus.ACTIVE
    assert result.created_at == now
    assert result.updated_at == now
    assert repo.get_by_id(result.id) == result


def test_create_client_validation_failure_when_trimmed_name_empty() -> None:
    repo = StubClientRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    use_case = CreateClientUseCase(client_repo=repo, clock=FixedClock(now))

    with pytest.raises(InvalidClientNameError, match="Client name is required"):
        use_case.execute(CreateClientCommand(name="   "))

