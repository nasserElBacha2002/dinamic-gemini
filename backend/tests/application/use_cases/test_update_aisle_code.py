"""Tests for UpdateAisleCodeUseCase."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.errors import AisleNotFoundError, DuplicateAisleCodeError
from src.application.ports.repositories import AisleRepository
from src.application.services.optional_unset import UNSET
from src.application.use_cases.aisles.update_aisle_code import (
    UpdateAisleCodeCommand,
    UpdateAisleCodeUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import AisleIdentificationMode


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: dict[str, Aisle] = {}
        self.save_calls = 0

    def save(self, aisle: Aisle) -> None:
        self.save_calls += 1
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code.strip():
                return a
        return None


def _aisle(
    now: datetime,
    *,
    aisle_id: str = "a1",
    inventory_id: str = "inv-1",
    code: str = "A01",
    identification_mode: AisleIdentificationMode | None = None,
) -> Aisle:
    return Aisle(
        id=aisle_id,
        inventory_id=inventory_id,
        code=code,
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        identification_mode=identification_mode,
    )


def test_update_aisle_code_success() -> None:
    created = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2025, 3, 7, 8, 0, 0, tzinfo=timezone.utc)
    repo = StubAisleRepo()
    repo.save(_aisle(created))
    repo.save_calls = 0
    uc = UpdateAisleCodeUseCase(aisle_repo=repo, clock=FixedClock(now))

    result = uc.execute(
        UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="a1", code="  B02  ")
    )

    assert result.code == "B02"
    assert result.updated_at == now
    assert repo.save_calls == 1


def test_update_aisle_code_rejects_empty() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    repo = StubAisleRepo()
    repo.save(_aisle(now))
    repo.save_calls = 0
    uc = UpdateAisleCodeUseCase(aisle_repo=repo, clock=FixedClock(now))

    with pytest.raises(ValueError, match="must not be empty"):
        uc.execute(UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="a1", code="   "))
    assert repo.save_calls == 0


def test_update_aisle_code_duplicate() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    repo = StubAisleRepo()
    repo.save(_aisle(now, aisle_id="a1", code="A01"))
    repo.save(_aisle(now, aisle_id="a2", code="B02"))
    repo.save_calls = 0
    uc = UpdateAisleCodeUseCase(aisle_repo=repo, clock=FixedClock(now))

    with pytest.raises(DuplicateAisleCodeError):
        uc.execute(UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="a1", code="B02"))
    assert repo.save_calls == 0


def test_update_aisle_code_noop_when_unchanged() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    later = datetime(2025, 3, 8, 1, 0, 0, tzinfo=timezone.utc)
    repo = StubAisleRepo()
    repo.save(_aisle(now, code="A01"))
    repo.save_calls = 0
    uc = UpdateAisleCodeUseCase(aisle_repo=repo, clock=FixedClock(later))

    result = uc.execute(
        UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="a1", code="  A01  ")
    )

    assert result.code == "A01"
    assert result.updated_at == now
    assert repo.save_calls == 0


def test_update_aisle_code_not_found() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    uc = UpdateAisleCodeUseCase(aisle_repo=StubAisleRepo(), clock=FixedClock(now))

    with pytest.raises(AisleNotFoundError):
        uc.execute(UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="missing", code="X"))


def test_update_aisle_partial_patch_identification_mode_only_leaves_code_unchanged() -> None:
    """Partial PATCH: omitting ``code`` must not require it (identification_mode alone is enough)."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    repo = StubAisleRepo()
    repo.save(_aisle(now, code="A01"))
    repo.save_calls = 0
    uc = UpdateAisleCodeUseCase(aisle_repo=repo, clock=FixedClock(now))

    result = uc.execute(
        UpdateAisleCodeCommand(
            inventory_id="inv-1",
            aisle_id="a1",
            code=None,
            identification_mode=AisleIdentificationMode.CODE_SCAN,
        )
    )

    assert result.code == "A01"
    assert result.identification_mode == AisleIdentificationMode.CODE_SCAN
    assert repo.save_calls == 1


def test_update_aisle_partial_patch_explicit_null_clears_identification_mode() -> None:
    """Explicit ``identification_mode=None`` clears the aisle override (inherit from inventory/client)."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    repo = StubAisleRepo()
    repo.save(_aisle(now, code="A01", identification_mode=AisleIdentificationMode.INTERNAL_OCR))
    repo.save_calls = 0
    uc = UpdateAisleCodeUseCase(aisle_repo=repo, clock=FixedClock(now))

    result = uc.execute(
        UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="a1", code=None, identification_mode=None)
    )

    assert result.identification_mode is None
    assert repo.save_calls == 1


def test_update_aisle_partial_patch_unset_identification_mode_is_noop_field() -> None:
    """Default ``UNSET`` identification_mode leaves the stored override untouched."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    repo = StubAisleRepo()
    repo.save(_aisle(now, code="A01", identification_mode=AisleIdentificationMode.INTERNAL_OCR))
    repo.save_calls = 0
    uc = UpdateAisleCodeUseCase(aisle_repo=repo, clock=FixedClock(now))

    result = uc.execute(UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="a1", code="B02"))

    assert result.identification_mode == AisleIdentificationMode.INTERNAL_OCR
    assert UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="a1", code="B02").identification_mode is UNSET


def test_update_aisle_partial_patch_requires_at_least_one_field() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    repo = StubAisleRepo()
    repo.save(_aisle(now))
    repo.save_calls = 0
    uc = UpdateAisleCodeUseCase(aisle_repo=repo, clock=FixedClock(now))

    with pytest.raises(ValueError, match="At least one field must be provided"):
        uc.execute(UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="a1"))
    assert repo.save_calls == 0


def test_update_aisle_partial_patch_invalid_identification_mode_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    repo = StubAisleRepo()
    repo.save(_aisle(now))
    repo.save_calls = 0
    uc = UpdateAisleCodeUseCase(aisle_repo=repo, clock=FixedClock(now))

    with pytest.raises(ValueError, match="Invalid identification_mode"):
        uc.execute(
            UpdateAisleCodeCommand(inventory_id="inv-1", aisle_id="a1", identification_mode="AUTO")
        )
    assert repo.save_calls == 0
