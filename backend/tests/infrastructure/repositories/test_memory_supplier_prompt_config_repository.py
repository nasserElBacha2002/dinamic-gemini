from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.infrastructure.repositories.memory_supplier_prompt_config_repository import (
    MemorySupplierPromptConfigRepository,
)


def _cfg(
    *,
    config_id: str,
    supplier_id: str,
    provider: str,
    model: str | None,
    version: int,
    active: bool,
    created_at: datetime,
) -> SupplierPromptConfig:
    return SupplierPromptConfig(
        id=config_id,
        client_supplier_id=supplier_id,
        provider_name=provider,
        model_name=model,
        instructions_text=f"instructions {config_id}",
        version=version,
        is_active=active,
        created_at=created_at,
        updated_at=created_at,
    )


def test_create_and_get_by_id() -> None:
    repo = MemorySupplierPromptConfigRepository()
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    cfg = _cfg(
        config_id="cfg-1",
        supplier_id="sup-1",
        provider="gemini",
        model=None,
        version=1,
        active=False,
        created_at=now,
    )
    repo.create(cfg)
    loaded = repo.get_by_id("cfg-1")
    assert loaded is not None
    assert loaded.id == "cfg-1"
    assert loaded.provider_name == "gemini"
    assert loaded.model_name is None


def test_list_by_supplier_is_deterministic() -> None:
    repo = MemorySupplierPromptConfigRepository()
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(
        _cfg(
            config_id="cfg-b",
            supplier_id="sup-1",
            provider="openai",
            model="gpt-4o",
            version=1,
            active=False,
            created_at=now,
        )
    )
    repo.create(
        _cfg(
            config_id="cfg-a-v2",
            supplier_id="sup-1",
            provider="gemini",
            model=None,
            version=2,
            active=False,
            created_at=now + timedelta(seconds=2),
        )
    )
    repo.create(
        _cfg(
            config_id="cfg-a-v1",
            supplier_id="sup-1",
            provider="gemini",
            model=None,
            version=1,
            active=False,
            created_at=now + timedelta(seconds=1),
        )
    )
    rows = repo.list_by_supplier("sup-1")
    assert [row.id for row in rows] == ["cfg-a-v2", "cfg-a-v1", "cfg-b"]


def test_scope_methods_keep_null_and_specific_model_distinct() -> None:
    repo = MemorySupplierPromptConfigRepository()
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(
        _cfg(
            config_id="cfg-default-v1",
            supplier_id="sup-1",
            provider="gemini",
            model=None,
            version=1,
            active=False,
            created_at=now,
        )
    )
    repo.create(
        _cfg(
            config_id="cfg-model-v1",
            supplier_id="sup-1",
            provider="gemini",
            model="gemini-2.0-flash-exp",
            version=1,
            active=False,
            created_at=now + timedelta(seconds=1),
        )
    )

    default_scope = repo.list_versions_by_scope("sup-1", "gemini", None)
    model_scope = repo.list_versions_by_scope("sup-1", "gemini", "gemini-2.0-flash-exp")
    assert [row.id for row in default_scope] == ["cfg-default-v1"]
    assert [row.id for row in model_scope] == ["cfg-model-v1"]


def test_latest_version_and_active_deactivate_activate_flow() -> None:
    repo = MemorySupplierPromptConfigRepository()
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(
        _cfg(
            config_id="cfg-v1",
            supplier_id="sup-1",
            provider="openai",
            model=None,
            version=1,
            active=True,
            created_at=now,
        )
    )
    repo.create(
        _cfg(
            config_id="cfg-v2",
            supplier_id="sup-1",
            provider="openai",
            model=None,
            version=2,
            active=False,
            created_at=now + timedelta(seconds=1),
        )
    )
    assert repo.get_latest_version_number("sup-1", "openai", None) == 2
    active = repo.get_active_by_scope("sup-1", "openai", None)
    assert active is not None and active.id == "cfg-v1"

    repo.deactivate_scope("sup-1", "openai", None)
    assert repo.get_active_by_scope("sup-1", "openai", None) is None

    activated = repo.activate_version("cfg-v2")
    assert activated is not None and activated.id == "cfg-v2" and activated.is_active is True
    active_after = repo.get_active_by_scope("sup-1", "openai", None)
    assert active_after is not None and active_after.id == "cfg-v2"


def test_uniqueness_invariants_are_enforced() -> None:
    repo = MemorySupplierPromptConfigRepository()
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(
        _cfg(
            config_id="cfg-1",
            supplier_id="sup-1",
            provider="gemini",
            model=None,
            version=1,
            active=True,
            created_at=now,
        )
    )
    with pytest.raises(ValueError):
        repo.create(
            _cfg(
                config_id="cfg-1",
                supplier_id="sup-1",
                provider="gemini",
                model=None,
                version=2,
                active=False,
                created_at=now + timedelta(seconds=1),
            )
        )
    with pytest.raises(ValueError):
        repo.create(
            _cfg(
                config_id="cfg-dup-version",
                supplier_id="sup-1",
                provider="gemini",
                model=None,
                version=1,
                active=False,
                created_at=now + timedelta(seconds=2),
            )
        )
    with pytest.raises(ValueError):
        repo.create(
            _cfg(
                config_id="cfg-dup-active",
                supplier_id="sup-1",
                provider="gemini",
                model=None,
                version=2,
                active=True,
                created_at=now + timedelta(seconds=3),
            )
        )
