"""Supplier prompt config use-case construction (Phase C4)."""

from __future__ import annotations

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    ClientRepository,
    ClientSupplierRepository,
    SupplierPromptConfigRepository,
)
from src.application.use_cases.manage_supplier_prompt_configs import (
    ActivateSupplierPromptConfigVersionUseCase,
    CreateSupplierPromptConfigVersionUseCase,
    GetActiveSupplierPromptConfigUseCase,
    GetSupplierPromptConfigUseCase,
    ListSupplierPromptConfigsUseCase,
)
from src.config import AppSettings


def build_list_supplier_prompt_configs_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    prompt_config_repo: SupplierPromptConfigRepository,
    settings: AppSettings,
) -> ListSupplierPromptConfigsUseCase:
    return ListSupplierPromptConfigsUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
        settings=settings,
    )


def build_create_supplier_prompt_config_version_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    prompt_config_repo: SupplierPromptConfigRepository,
    clock: Clock,
    settings: AppSettings,
) -> CreateSupplierPromptConfigVersionUseCase:
    return CreateSupplierPromptConfigVersionUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
        clock=clock,
        settings=settings,
    )


def build_get_active_supplier_prompt_config_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    prompt_config_repo: SupplierPromptConfigRepository,
    settings: AppSettings,
) -> GetActiveSupplierPromptConfigUseCase:
    return GetActiveSupplierPromptConfigUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
        settings=settings,
    )


def build_activate_supplier_prompt_config_version_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    prompt_config_repo: SupplierPromptConfigRepository,
) -> ActivateSupplierPromptConfigVersionUseCase:
    return ActivateSupplierPromptConfigVersionUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
    )


def build_get_supplier_prompt_config_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    prompt_config_repo: SupplierPromptConfigRepository,
) -> GetSupplierPromptConfigUseCase:
    return GetSupplierPromptConfigUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
    )
