from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    GlobalPromptConfigEmptyInstructionsError,
    GlobalPromptConfigInvalidScopeError,
    GlobalPromptConfigNotFoundError,
)
from src.application.use_cases.manage_global_prompt_configs import (
    ActivateGlobalPromptConfigVersionCommand,
    ActivateGlobalPromptConfigVersionUseCase,
    CreateGlobalPromptConfigVersionCommand,
    CreateGlobalPromptConfigVersionUseCase,
    GetActiveGlobalPromptConfigCommand,
    GetActiveGlobalPromptConfigUseCase,
    GetGlobalPromptConfigCommand,
    GetGlobalPromptConfigUseCase,
    ListGlobalPromptConfigsCommand,
    ListGlobalPromptConfigsUseCase,
)
from src.infrastructure.repositories.memory_global_prompt_config_repository import (
    MemoryGlobalPromptConfigRepository,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _deps():
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    return MemoryGlobalPromptConfigRepository(), FixedClock(now)


def test_create_first_version_active_by_default() -> None:
    repo, clock = _deps()
    uc = CreateGlobalPromptConfigVersionUseCase(repo, clock)
    created = uc.execute(
        CreateGlobalPromptConfigVersionCommand(
            instructions_text="Base global instructions.",
            activate=True,
        )
    )
    assert created.version == 1
    assert created.is_active is True


def test_create_second_active_version_deactivates_previous() -> None:
    repo, clock = _deps()
    uc = CreateGlobalPromptConfigVersionUseCase(repo, clock)
    v1 = uc.execute(CreateGlobalPromptConfigVersionCommand(instructions_text="v1", activate=True))
    v2 = uc.execute(CreateGlobalPromptConfigVersionCommand(instructions_text="v2", activate=True))
    assert v2.version == 2
    assert v2.is_active is True
    old = repo.get_by_id(v1.id)
    assert old is not None and old.is_active is False


def test_create_inactive_preserves_current_active() -> None:
    repo, clock = _deps()
    uc = CreateGlobalPromptConfigVersionUseCase(repo, clock)
    v1 = uc.execute(CreateGlobalPromptConfigVersionCommand(instructions_text="v1", activate=True))
    v2 = uc.execute(CreateGlobalPromptConfigVersionCommand(instructions_text="v2", activate=False))
    assert v2.version == 2
    assert v2.is_active is False
    active = repo.get_active()
    assert active is not None and active.id == v1.id


def test_activate_existing_version() -> None:
    repo, clock = _deps()
    create_uc = CreateGlobalPromptConfigVersionUseCase(repo, clock)
    v1 = create_uc.execute(CreateGlobalPromptConfigVersionCommand(instructions_text="v1", activate=True))
    v2 = create_uc.execute(CreateGlobalPromptConfigVersionCommand(instructions_text="v2", activate=False))
    activate_uc = ActivateGlobalPromptConfigVersionUseCase(repo)
    activated = activate_uc.execute(ActivateGlobalPromptConfigVersionCommand(config_id=v2.id))
    assert activated.id == v2.id
    assert activated.is_active is True
    assert repo.get_by_id(v1.id) is not None and repo.get_by_id(v1.id).is_active is False


def test_blank_instructions_rejected() -> None:
    repo, clock = _deps()
    uc = CreateGlobalPromptConfigVersionUseCase(repo, clock)
    with pytest.raises(GlobalPromptConfigEmptyInstructionsError):
        uc.execute(CreateGlobalPromptConfigVersionCommand(instructions_text="   ", activate=True))


def test_get_active_returns_none_when_no_active() -> None:
    repo, clock = _deps()
    create_uc = CreateGlobalPromptConfigVersionUseCase(repo, clock)
    get_active_uc = GetActiveGlobalPromptConfigUseCase(repo)
    create_uc.execute(CreateGlobalPromptConfigVersionCommand(instructions_text="inactive", activate=False))
    assert get_active_uc.execute(GetActiveGlobalPromptConfigCommand()) is None


def test_list_scope_validation_rejects_provider_or_model_in_phase_d9() -> None:
    repo, _ = _deps()
    list_uc = ListGlobalPromptConfigsUseCase(repo)
    with pytest.raises(GlobalPromptConfigInvalidScopeError):
        list_uc.execute(ListGlobalPromptConfigsCommand(provider_name="gemini"))
    with pytest.raises(GlobalPromptConfigInvalidScopeError):
        list_uc.execute(ListGlobalPromptConfigsCommand(model_name="gemini-2.0-flash-exp"))


def test_get_by_id_not_found_raises() -> None:
    repo, _ = _deps()
    uc = GetGlobalPromptConfigUseCase(repo)
    with pytest.raises(GlobalPromptConfigNotFoundError):
        uc.execute(GetGlobalPromptConfigCommand(config_id="missing"))
