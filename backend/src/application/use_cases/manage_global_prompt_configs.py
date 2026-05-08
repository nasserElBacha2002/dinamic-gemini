"""Global prompt-config use cases — Phase D9 application layer."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.application.errors import (
    GlobalPromptConfigActivationFailedError,
    GlobalPromptConfigEmptyInstructionsError,
    GlobalPromptConfigInvalidScopeError,
    GlobalPromptConfigNotFoundError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import GlobalPromptConfigRepository
from src.domain.global_prompt_config import GlobalPromptConfig

GLOBAL_SCOPE_TYPE = "global"


@dataclass
class CreateGlobalPromptConfigVersionCommand:
    instructions_text: str
    activate: bool = True


@dataclass
class ListGlobalPromptConfigsCommand:
    scope_type: str = GLOBAL_SCOPE_TYPE
    provider_name: str | None = None
    model_name: str | None = None


@dataclass
class GetActiveGlobalPromptConfigCommand:
    scope_type: str = GLOBAL_SCOPE_TYPE
    provider_name: str | None = None
    model_name: str | None = None


@dataclass
class ActivateGlobalPromptConfigVersionCommand:
    config_id: str


@dataclass
class GetGlobalPromptConfigCommand:
    config_id: str


def _normalize_optional_string(value: str | None) -> str | None:
    return (value or "").strip() or None


def _normalize_scope(scope_type: str) -> str:
    normalized = (scope_type or "").strip().lower() or GLOBAL_SCOPE_TYPE
    if normalized != GLOBAL_SCOPE_TYPE:
        raise GlobalPromptConfigInvalidScopeError("scope_type must be 'global'")
    return normalized


def _validate_scope(scope_type: str, provider_name: str | None, model_name: str | None) -> None:
    normalized_scope = _normalize_scope(scope_type)
    normalized_provider = _normalize_optional_string(provider_name)
    normalized_model = _normalize_optional_string(model_name)
    if normalized_scope != GLOBAL_SCOPE_TYPE:
        raise GlobalPromptConfigInvalidScopeError("scope_type must be 'global'")
    if normalized_provider is not None or normalized_model is not None:
        raise GlobalPromptConfigInvalidScopeError(
            "provider_name and model_name are not supported for global scope in this phase"
        )


def _ensure_non_empty_instructions(instructions_text: str) -> None:
    if not (instructions_text or "").strip():
        raise GlobalPromptConfigEmptyInstructionsError("instructions_text is required")


class ListGlobalPromptConfigsUseCase:
    def __init__(self, prompt_config_repo: GlobalPromptConfigRepository) -> None:
        self._prompt_config_repo = prompt_config_repo

    def execute(self, command: ListGlobalPromptConfigsCommand) -> list[GlobalPromptConfig]:
        _validate_scope(command.scope_type, command.provider_name, command.model_name)
        return list(
            self._prompt_config_repo.list_versions(
                scope_type=GLOBAL_SCOPE_TYPE,
                provider_name=None,
                model_name=None,
            )
        )


class CreateGlobalPromptConfigVersionUseCase:
    def __init__(self, prompt_config_repo: GlobalPromptConfigRepository, clock: Clock) -> None:
        self._prompt_config_repo = prompt_config_repo
        self._clock = clock

    def execute(self, command: CreateGlobalPromptConfigVersionCommand) -> GlobalPromptConfig:
        _ensure_non_empty_instructions(command.instructions_text)
        normalized_instructions_text = command.instructions_text.strip()

        latest_version = self._prompt_config_repo.get_latest_version_number(
            scope_type=GLOBAL_SCOPE_TYPE,
            provider_name=None,
            model_name=None,
        )
        next_version = 1 if latest_version is None else int(latest_version) + 1

        now = self._clock.now()
        created = self._prompt_config_repo.create(
            GlobalPromptConfig(
                id=str(uuid4()),
                scope_type=GLOBAL_SCOPE_TYPE,
                provider_name=None,
                model_name=None,
                instructions_text=normalized_instructions_text,
                version=next_version,
                is_active=False,
                created_at=now,
                updated_at=now,
            )
        )
        # Note: create + activate is not wrapped in a broader application transaction.
        # If activation fails after create, a new inactive version can remain persisted.
        # Repository invariants still guarantee one-active-per-scope safety.
        if not command.activate:
            return created
        activated = self._prompt_config_repo.activate_version(created.id)
        if activated is None:
            raise GlobalPromptConfigActivationFailedError(
                f"Failed to activate created global prompt config: {created.id}"
            )
        return activated


class GetActiveGlobalPromptConfigUseCase:
    def __init__(self, prompt_config_repo: GlobalPromptConfigRepository) -> None:
        self._prompt_config_repo = prompt_config_repo

    def execute(self, command: GetActiveGlobalPromptConfigCommand) -> GlobalPromptConfig | None:
        _validate_scope(command.scope_type, command.provider_name, command.model_name)
        return self._prompt_config_repo.get_active(
            scope_type=GLOBAL_SCOPE_TYPE,
            provider_name=None,
            model_name=None,
        )


class ActivateGlobalPromptConfigVersionUseCase:
    def __init__(self, prompt_config_repo: GlobalPromptConfigRepository) -> None:
        self._prompt_config_repo = prompt_config_repo

    def execute(self, command: ActivateGlobalPromptConfigVersionCommand) -> GlobalPromptConfig:
        existing = self._prompt_config_repo.get_by_id(command.config_id)
        if existing is None:
            raise GlobalPromptConfigNotFoundError(
                f"Global prompt config not found: {command.config_id}"
            )
        _validate_scope(existing.scope_type, existing.provider_name, existing.model_name)
        activated = self._prompt_config_repo.activate_version(command.config_id)
        if activated is None:
            raise GlobalPromptConfigActivationFailedError(
                f"Failed to activate global prompt config: {command.config_id}"
            )
        return activated


class GetGlobalPromptConfigUseCase:
    def __init__(self, prompt_config_repo: GlobalPromptConfigRepository) -> None:
        self._prompt_config_repo = prompt_config_repo

    def execute(self, command: GetGlobalPromptConfigCommand) -> GlobalPromptConfig:
        config = self._prompt_config_repo.get_by_id(command.config_id)
        if config is None:
            raise GlobalPromptConfigNotFoundError(
                f"Global prompt config not found: {command.config_id}"
            )
        _validate_scope(config.scope_type, config.provider_name, config.model_name)
        return config
