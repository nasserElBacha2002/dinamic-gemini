from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    ClientSupplierClientMismatchError,
    SupplierPromptConfigEmptyInstructionsError,
    SupplierPromptConfigInvalidModelError,
    SupplierPromptConfigInvalidProviderError,
    SupplierPromptConfigInvalidScopeError,
    SupplierPromptConfigNotFoundError,
)
from src.application.use_cases.suppliers.manage_supplier_prompt_configs import (
    ActivateSupplierPromptConfigVersionCommand,
    ActivateSupplierPromptConfigVersionUseCase,
    CreateSupplierPromptConfigVersionCommand,
    CreateSupplierPromptConfigVersionUseCase,
    GetActiveSupplierPromptConfigCommand,
    GetActiveSupplierPromptConfigUseCase,
    GetSupplierPromptConfigCommand,
    GetSupplierPromptConfigUseCase,
    ListSupplierPromptConfigsCommand,
    ListSupplierPromptConfigsUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_supplier_prompt_config_repository import (
    MemorySupplierPromptConfigRepository,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubSettings:
    processing_gemini_models = "gemini-2.0-flash-exp,gemini-1.5-pro"
    gemini_model_name = "gemini-2.0-flash-exp"
    processing_openai_models = "gpt-4o,gpt-4.1"
    openai_model = "gpt-4o"
    processing_claude_models = "claude-sonnet-4-20250514"
    anthropic_model = "claude-sonnet-4-20250514"
    processing_deepseek_models = "deepseek-chat"
    deepseek_model = "deepseek-chat"


def _deps():
    now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = MemoryClientRepository()
    supplier_repo = MemoryClientSupplierRepository()
    prompt_repo = MemorySupplierPromptConfigRepository()
    client_repo.save(
        Client(
            id="client-1",
            name="Client 1",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    supplier_repo.save(
        ClientSupplier(
            id="supplier-1",
            client_id="client-1",
            name="Supplier 1",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    supplier_repo.save(
        ClientSupplier(
            id="supplier-2",
            client_id="client-2",
            name="Supplier 2",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    return client_repo, supplier_repo, prompt_repo, FixedClock(now), StubSettings()


def test_create_first_version_active_by_default() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    created = uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="Use supplier hints.",
            activate=True,
        )
    )
    assert created.version == 1
    assert created.is_active is True
    active = prompt_repo.get_active_by_scope("supplier-1", "gemini", None)
    assert active is not None and active.id == created.id


def test_create_second_version_increments_and_activates() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    v1 = uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="v1",
            activate=True,
        )
    )
    v2 = uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="v2",
            activate=True,
        )
    )
    assert v2.version == 2
    assert v2.is_active is True
    assert prompt_repo.get_latest_version_number("supplier-1", "gemini", None) == 2
    old_v1 = prompt_repo.get_by_id(v1.id)
    assert old_v1 is not None and old_v1.is_active is False


def test_create_second_version_without_activation_keeps_previous_active() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    v1 = uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="v1",
            activate=True,
        )
    )
    v2 = uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="v2",
            activate=False,
        )
    )
    assert v2.version == 2
    assert v2.is_active is False
    active = prompt_repo.get_active_by_scope("supplier-1", "gemini", None)
    assert active is not None and active.id == v1.id


def test_default_and_model_specific_scopes_stay_independent() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    create_uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    default_v1 = create_uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="default v1",
            activate=True,
        )
    )
    model_v1 = create_uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name="gemini-2.0-flash-exp",
            instructions_text="model v1",
            activate=True,
        )
    )
    default_v2 = create_uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="default v2",
            activate=True,
        )
    )
    assert default_v1.id != default_v2.id
    active_default = prompt_repo.get_active_by_scope("supplier-1", "gemini", None)
    active_model = prompt_repo.get_active_by_scope(
        "supplier-1", "gemini", "gemini-2.0-flash-exp"
    )
    assert active_default is not None and active_default.id == default_v2.id
    assert active_model is not None and active_model.id == model_v1.id


def test_ownership_validation_rejects_supplier_from_other_client() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    create_uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    list_uc = ListSupplierPromptConfigsUseCase(
        client_repo, supplier_repo, prompt_repo, settings
    )
    with pytest.raises(ClientSupplierClientMismatchError):
        create_uc.execute(
            CreateSupplierPromptConfigVersionCommand(
                client_id="client-1",
                supplier_id="supplier-2",
                provider_name="gemini",
                model_name=None,
                instructions_text="x",
                activate=True,
            )
        )
    with pytest.raises(ClientSupplierClientMismatchError):
        list_uc.execute(
            ListSupplierPromptConfigsCommand(
                client_id="client-1",
                supplier_id="supplier-2",
            )
        )


def test_activation_rejects_config_from_different_supplier_scope() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    create_uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    created = create_uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="scope test",
            activate=False,
        )
    )
    activate_uc = ActivateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo
    )
    with pytest.raises(ClientSupplierClientMismatchError):
        activate_uc.execute(
            ActivateSupplierPromptConfigVersionCommand(
                client_id="client-1",
                supplier_id="supplier-2",
                config_id=created.id,
            )
        )

    supplier_repo.save(
        ClientSupplier(
            id="supplier-3",
            client_id="client-1",
            name="Supplier 3",
            status=ClientSupplierStatus.ACTIVE,
            created_at=clock.now(),
            updated_at=clock.now(),
        )
    )
    with pytest.raises(SupplierPromptConfigNotFoundError):
        activate_uc.execute(
            ActivateSupplierPromptConfigVersionCommand(
                client_id="client-1",
                supplier_id="supplier-3",
                config_id=created.id,
            )
        )


def test_invalid_provider_rejected() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    with pytest.raises(SupplierPromptConfigInvalidProviderError):
        uc.execute(
            CreateSupplierPromptConfigVersionCommand(
                client_id="client-1",
                supplier_id="supplier-1",
                provider_name="unsupported-provider",
                model_name=None,
                instructions_text="x",
                activate=True,
            )
        )


def test_invalid_model_rejected_for_provider() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    with pytest.raises(SupplierPromptConfigInvalidModelError):
        uc.execute(
            CreateSupplierPromptConfigVersionCommand(
                client_id="client-1",
                supplier_id="supplier-1",
                provider_name="gemini",
                model_name="gpt-4o",
                instructions_text="x",
                activate=True,
            )
        )


def test_blank_instructions_rejected() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    with pytest.raises(SupplierPromptConfigEmptyInstructionsError):
        uc.execute(
            CreateSupplierPromptConfigVersionCommand(
                client_id="client-1",
                supplier_id="supplier-1",
                provider_name="gemini",
                model_name=None,
                instructions_text="   ",
                activate=True,
            )
        )


def test_normalization_and_scope_for_versioning() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    create_uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    get_active_uc = GetActiveSupplierPromptConfigUseCase(
        client_repo, supplier_repo, prompt_repo, settings
    )
    v1 = create_uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name=" gemini ",
            model_name="   ",
            instructions_text="v1",
            activate=True,
        )
    )
    v2 = create_uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="v2",
            activate=False,
        )
    )
    assert v1.provider_name == "gemini"
    assert v1.model_name is None
    assert v2.version == 2

    active = get_active_uc.execute(
        GetActiveSupplierPromptConfigCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
        )
    )
    assert active is not None and active.id == v1.id


def test_list_rejects_model_without_provider() -> None:
    client_repo, supplier_repo, prompt_repo, _, settings = _deps()
    list_uc = ListSupplierPromptConfigsUseCase(
        client_repo, supplier_repo, prompt_repo, settings
    )
    with pytest.raises(SupplierPromptConfigInvalidScopeError):
        list_uc.execute(
            ListSupplierPromptConfigsCommand(
                client_id="client-1",
                supplier_id="supplier-1",
                provider_name=None,
                model_name="gemini-2.0-flash-exp",
            )
        )


def test_list_rejects_invalid_provider_when_filtering() -> None:
    client_repo, supplier_repo, prompt_repo, _, settings = _deps()
    list_uc = ListSupplierPromptConfigsUseCase(
        client_repo, supplier_repo, prompt_repo, settings
    )
    with pytest.raises(SupplierPromptConfigInvalidProviderError):
        list_uc.execute(
            ListSupplierPromptConfigsCommand(
                client_id="client-1",
                supplier_id="supplier-1",
                provider_name="unsupported-provider",
                model_name=None,
            )
        )


def test_list_rejects_invalid_model_for_provider() -> None:
    client_repo, supplier_repo, prompt_repo, _, settings = _deps()
    list_uc = ListSupplierPromptConfigsUseCase(
        client_repo, supplier_repo, prompt_repo, settings
    )
    with pytest.raises(SupplierPromptConfigInvalidModelError):
        list_uc.execute(
            ListSupplierPromptConfigsCommand(
                client_id="client-1",
                supplier_id="supplier-1",
                provider_name="gemini",
                model_name="gpt-4o",
            )
        )


def test_get_supplier_prompt_config_rejects_config_outside_supplier_scope() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    create_uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    created = create_uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="scope test",
            activate=False,
        )
    )
    supplier_repo.save(
        ClientSupplier(
            id="supplier-3",
            client_id="client-1",
            name="Supplier 3",
            status=ClientSupplierStatus.ACTIVE,
            created_at=clock.now(),
            updated_at=clock.now(),
        )
    )
    get_uc = GetSupplierPromptConfigUseCase(client_repo, supplier_repo, prompt_repo)
    with pytest.raises(SupplierPromptConfigNotFoundError):
        get_uc.execute(
            GetSupplierPromptConfigCommand(
                client_id="client-1",
                supplier_id="supplier-3",
                config_id=created.id,
            )
        )


def test_create_trims_outer_whitespace_from_instructions() -> None:
    client_repo, supplier_repo, prompt_repo, clock, settings = _deps()
    uc = CreateSupplierPromptConfigVersionUseCase(
        client_repo, supplier_repo, prompt_repo, clock, settings
    )
    created = uc.execute(
        CreateSupplierPromptConfigVersionCommand(
            client_id="client-1",
            supplier_id="supplier-1",
            provider_name="gemini",
            model_name=None,
            instructions_text="  line 1\nline 2  ",
            activate=False,
        )
    )
    assert created.instructions_text == "line 1\nline 2"
