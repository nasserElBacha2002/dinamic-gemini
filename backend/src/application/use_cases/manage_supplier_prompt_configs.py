"""Supplier prompt-config use cases — Phase D3 application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from src.application.errors import (
    ClientNotFoundError,
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
    SupplierPromptConfigActivationFailedError,
    SupplierPromptConfigEmptyInstructionsError,
    SupplierPromptConfigInvalidModelError,
    SupplierPromptConfigInvalidProviderError,
    SupplierPromptConfigInvalidScopeError,
    SupplierPromptConfigNotFoundError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    ClientRepository,
    ClientSupplierRepository,
    SupplierPromptConfigRepository,
)
from src.application.services.processing_experiment_catalog import normalize_requested_model
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.pipeline.providers.definitions import registered_pipeline_provider_keys_from_definitions


@dataclass
class CreateSupplierPromptConfigVersionCommand:
    client_id: str
    supplier_id: str
    provider_name: str | None
    model_name: str | None
    instructions_text: str
    activate: bool = True


@dataclass
class ListSupplierPromptConfigsCommand:
    client_id: str
    supplier_id: str
    provider_name: str | None = None
    model_name: str | None = None
    scope: str | None = None


@dataclass
class GetActiveSupplierPromptConfigCommand:
    client_id: str
    supplier_id: str
    provider_name: str | None
    model_name: str | None


@dataclass
class ActivateSupplierPromptConfigVersionCommand:
    client_id: str
    supplier_id: str
    config_id: str


@dataclass
class GetSupplierPromptConfigCommand:
    client_id: str
    supplier_id: str
    config_id: str


def _normalize_optional_provider(provider_name: str | None) -> str | None:
    normalized = (provider_name or "").strip().lower()
    return normalized or None


def _normalize_model(model_name: str | None) -> str | None:
    return (model_name or "").strip() or None


def _ensure_non_empty_instructions(instructions_text: str) -> None:
    if not (instructions_text or "").strip():
        raise SupplierPromptConfigEmptyInstructionsError("instructions_text is required")


def _validate_provider_model_scope(
    *,
    provider_name: str | None,
    model_name: str | None,
    settings: Any,
) -> None:
    if provider_name is None:
        if model_name is not None:
            raise SupplierPromptConfigInvalidScopeError(
                "provider_name is required when model_name is provided"
            )
        return
    known = registered_pipeline_provider_keys_from_definitions()
    if provider_name not in known:
        raise SupplierPromptConfigInvalidProviderError(
            f"Unknown provider_name {provider_name!r}. Known keys: {sorted(known)}"
        )
    if model_name is None:
        return
    resolved = normalize_requested_model(provider_name, model_name, settings)
    if resolved is None:
        raise SupplierPromptConfigInvalidModelError(
            f"Model {model_name!r} is not available for provider {provider_name!r}"
        )


def _validate_supplier_in_client_scope(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    client_id: str,
    supplier_id: str,
) -> None:
    client = client_repo.get_by_id(client_id)
    if client is None:
        raise ClientNotFoundError(f"Client not found: {client_id}")
    supplier = client_supplier_repo.get_by_id(supplier_id)
    if supplier is None:
        raise ClientSupplierNotFoundError(f"Client supplier not found: {supplier_id}")
    if supplier.client_id != client_id:
        raise ClientSupplierClientMismatchError(
            "Client supplier does not belong to the requested client"
        )


class ListSupplierPromptConfigsUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        prompt_config_repo: SupplierPromptConfigRepository,
        settings: Any,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._prompt_config_repo = prompt_config_repo
        self._settings = settings

    def execute(self, command: ListSupplierPromptConfigsCommand) -> list[SupplierPromptConfig]:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        provider_name = (
            _normalize_optional_provider(command.provider_name)
            if command.provider_name is not None
            else None
        )
        model_name = _normalize_model(command.model_name)
        scope = (command.scope or "").strip().lower() or None
        if scope not in (None, "all"):
            raise SupplierPromptConfigInvalidScopeError(
                "scope must be 'all' when provided"
            )
        if scope == "all" and (provider_name is not None or model_name is not None):
            raise SupplierPromptConfigInvalidScopeError(
                "scope=all cannot be combined with provider_name/model_name"
            )
        if provider_name is None and model_name is not None:
            raise SupplierPromptConfigInvalidScopeError(
                "provider_name is required when model_name is provided"
            )
        if scope is None and provider_name is None and model_name is None:
            return list(self._prompt_config_repo.list_by_supplier(command.supplier_id))
        if scope == "all":
            return list(
                self._prompt_config_repo.list_versions_by_scope(
                    command.supplier_id, None, None
                )
            )
        _validate_provider_model_scope(
            provider_name=provider_name,
            model_name=model_name,
            settings=self._settings,
        )
        return list(
            self._prompt_config_repo.list_versions_by_scope(
                command.supplier_id,
                provider_name,
                model_name,
            )
        )


class CreateSupplierPromptConfigVersionUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        prompt_config_repo: SupplierPromptConfigRepository,
        clock: Clock,
        settings: Any,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._prompt_config_repo = prompt_config_repo
        self._clock = clock
        self._settings = settings

    def execute(self, command: CreateSupplierPromptConfigVersionCommand) -> SupplierPromptConfig:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        provider_name = _normalize_optional_provider(command.provider_name)
        model_name = _normalize_model(command.model_name)
        _ensure_non_empty_instructions(command.instructions_text)
        normalized_instructions_text = command.instructions_text.strip()
        _validate_provider_model_scope(
            provider_name=provider_name,
            model_name=model_name,
            settings=self._settings,
        )

        latest_version = self._prompt_config_repo.get_latest_version_number(
            command.supplier_id,
            provider_name,
            model_name,
        )
        next_version = 1 if latest_version is None else int(latest_version) + 1

        now = self._clock.now()
        created = self._prompt_config_repo.create(
            SupplierPromptConfig(
                id=str(uuid4()),
                client_supplier_id=command.supplier_id,
                provider_name=provider_name,
                model_name=model_name,
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
            raise SupplierPromptConfigActivationFailedError(
                f"Failed to activate created supplier prompt config: {created.id}"
            )
        return activated


class GetActiveSupplierPromptConfigUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        prompt_config_repo: SupplierPromptConfigRepository,
        settings: Any,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._prompt_config_repo = prompt_config_repo
        self._settings = settings

    def execute(
        self, command: GetActiveSupplierPromptConfigCommand
    ) -> SupplierPromptConfig | None:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        provider_name = _normalize_optional_provider(command.provider_name)
        model_name = _normalize_model(command.model_name)
        _validate_provider_model_scope(
            provider_name=provider_name,
            model_name=model_name,
            settings=self._settings,
        )
        return self._prompt_config_repo.get_active_by_scope(
            command.supplier_id,
            provider_name,
            model_name,
        )


class ActivateSupplierPromptConfigVersionUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        prompt_config_repo: SupplierPromptConfigRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._prompt_config_repo = prompt_config_repo

    def execute(
        self, command: ActivateSupplierPromptConfigVersionCommand
    ) -> SupplierPromptConfig:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        existing = self._prompt_config_repo.get_by_id(command.config_id)
        if existing is None:
            raise SupplierPromptConfigNotFoundError(
                f"Supplier prompt config not found: {command.config_id}"
            )
        if existing.client_supplier_id != command.supplier_id:
            raise SupplierPromptConfigNotFoundError(
                f"Supplier prompt config not found in supplier scope: {command.config_id}"
            )
        activated = self._prompt_config_repo.activate_version(command.config_id)
        if activated is None:
            raise SupplierPromptConfigActivationFailedError(
                f"Failed to activate supplier prompt config: {command.config_id}"
            )
        return activated


class GetSupplierPromptConfigUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        prompt_config_repo: SupplierPromptConfigRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._prompt_config_repo = prompt_config_repo

    def execute(self, command: GetSupplierPromptConfigCommand) -> SupplierPromptConfig:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        config = self._prompt_config_repo.get_by_id(command.config_id)
        if config is None or config.client_supplier_id != command.supplier_id:
            raise SupplierPromptConfigNotFoundError(
                f"Supplier prompt config not found in supplier scope: {command.config_id}"
            )
        return config
