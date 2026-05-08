from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.domain.global_prompt_config import GlobalPromptConfig
from src.infrastructure.repositories.memory_global_prompt_config_repository import (
    MemoryGlobalPromptConfigRepository,
)


def _cfg(
    *,
    config_id: str,
    version: int,
    active: bool,
    created_at: datetime,
) -> GlobalPromptConfig:
    return GlobalPromptConfig(
        id=config_id,
        scope_type="global",
        provider_name=None,
        model_name=None,
        instructions_text=f"instructions {config_id}",
        version=version,
        is_active=active,
        created_at=created_at,
        updated_at=created_at,
    )


def test_create_and_get_by_id() -> None:
    repo = MemoryGlobalPromptConfigRepository()
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    cfg = _cfg(config_id="cfg-1", version=1, active=False, created_at=now)
    repo.create(cfg)
    loaded = repo.get_by_id("cfg-1")
    assert loaded is not None
    assert loaded.scope_type == "global"
    assert loaded.provider_name is None
    assert loaded.model_name is None


def test_list_versions_is_deterministic() -> None:
    repo = MemoryGlobalPromptConfigRepository()
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(_cfg(config_id="cfg-v2", version=2, active=False, created_at=now + timedelta(seconds=2)))
    repo.create(_cfg(config_id="cfg-v1", version=1, active=False, created_at=now + timedelta(seconds=1)))
    rows = repo.list_versions()
    assert [row.id for row in rows] == ["cfg-v2", "cfg-v1"]


def test_latest_version_and_active_deactivate_activate_flow() -> None:
    repo = MemoryGlobalPromptConfigRepository()
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(_cfg(config_id="cfg-v1", version=1, active=True, created_at=now))
    repo.create(_cfg(config_id="cfg-v2", version=2, active=False, created_at=now + timedelta(seconds=1)))
    assert repo.get_latest_version_number() == 2
    active = repo.get_active()
    assert active is not None and active.id == "cfg-v1"

    repo.deactivate_scope()
    assert repo.get_active() is None

    activated = repo.activate_version("cfg-v2")
    assert activated is not None and activated.id == "cfg-v2" and activated.is_active is True


def test_uniqueness_invariants_are_enforced() -> None:
    repo = MemoryGlobalPromptConfigRepository()
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(_cfg(config_id="cfg-1", version=1, active=True, created_at=now))

    with pytest.raises(ValueError):
        repo.create(_cfg(config_id="cfg-1", version=2, active=False, created_at=now + timedelta(seconds=1)))
    with pytest.raises(ValueError):
        repo.create(_cfg(config_id="cfg-dup-version", version=1, active=False, created_at=now + timedelta(seconds=2)))
    with pytest.raises(ValueError):
        repo.create(_cfg(config_id="cfg-dup-active", version=2, active=True, created_at=now + timedelta(seconds=3)))
