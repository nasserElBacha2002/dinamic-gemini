"""
Supplier prompt configuration resolution for pipeline jobs — Phase E2.

Resolves **which** active `supplier_prompt_configs` row would apply for a given inventory, aisle,
and provider/model. Does **not** modify LLM prompts, adapters, or persistence (E3/E4/E6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.application.ports.repositories import (
    AisleRepository,
    ClientSupplierRepository,
    InventoryRepository,
    SupplierPromptConfigRepository,
)
from src.domain.client_supplier.prompt_config import SupplierPromptConfig

ResolutionStatus = Literal["resolved", "fallback", "error"]


class SupplierPromptFallbackReason:
    """Stable string reasons when ``fallback_used`` is true (legacy / no config)."""

    INVENTORY_WITHOUT_CLIENT = "INVENTORY_WITHOUT_CLIENT"
    AISLE_WITHOUT_CLIENT_SUPPLIER = "AISLE_WITHOUT_CLIENT_SUPPLIER"
    NO_ACTIVE_SUPPLIER_PROMPT_CONFIG = "NO_ACTIVE_SUPPLIER_PROMPT_CONFIG"


class SupplierPromptResolutionErrorCode:
    """Stable codes when ``resolution_status == \"error\"``."""

    INVENTORY_NOT_FOUND = "INVENTORY_NOT_FOUND"
    AISLE_NOT_FOUND = "AISLE_NOT_FOUND"
    AISLE_INVENTORY_MISMATCH = "AISLE_INVENTORY_MISMATCH"
    CLIENT_SUPPLIER_NOT_FOUND = "CLIENT_SUPPLIER_NOT_FOUND"
    CLIENT_SUPPLIER_OWNERSHIP_MISMATCH = "CLIENT_SUPPLIER_OWNERSHIP_MISMATCH"
    INVALID_SCOPE_INPUT = "INVALID_SCOPE_INPUT"
    NO_ACTIVE_SUPPLIER_PROMPT_CONFIG = "NO_ACTIVE_SUPPLIER_PROMPT_CONFIG"


def _normalize_provider(provider_name: str | None) -> str | None:
    return (provider_name or "").strip().lower() or None


def _normalize_model(model_name: str | None) -> str | None:
    return (model_name or "").strip() or None


def _resolve_active_with_precedence(
    repo: SupplierPromptConfigRepository,
    client_supplier_id: str,
    provider_name: str | None,
    model_name: str | None,
) -> SupplierPromptConfig | None:
    """
    Precedence (within one ``client_supplier_id``):

    1. Exact provider + exact model (when both requested).
    2. Provider default (requested provider, ``model_name`` NULL in DB).
    3. Supplier-wide all-provider default (both NULL in DB).

    Never searches outside ``client_supplier_id``.
    """
    if provider_name is not None and model_name is not None:
        hit = repo.get_active_by_scope(client_supplier_id, provider_name, model_name)
        if hit is not None:
            return hit
    if provider_name is not None:
        hit = repo.get_active_by_scope(client_supplier_id, provider_name, None)
        if hit is not None:
            return hit
    return repo.get_active_by_scope(client_supplier_id, None, None)


@dataclass(frozen=True)
class SupplierPromptResolution:
    """Auditable result of supplier prompt scope resolution (Phase E2)."""

    inventory_id: str
    aisle_id: str
    client_id: str | None
    client_supplier_id: str | None
    provider_name: str | None
    model_name: str | None
    supplier_prompt_config_id: str | None
    supplier_prompt_config_version: int | None
    editable_instructions: str | None
    fallback_used: bool
    fallback_reason: str | None
    resolution_status: ResolutionStatus
    warnings: tuple[str, ...] = field(default_factory=tuple)
    error_code: str | None = None


class SupplierPromptResolver:
    """Resolve supplier prompt config context for an inventory + aisle + provider/model (E2)."""

    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        client_supplier_repo: ClientSupplierRepository,
        supplier_prompt_config_repo: SupplierPromptConfigRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._client_supplier_repo = client_supplier_repo
        self._supplier_prompt_config_repo = supplier_prompt_config_repo

    def resolve(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        provider_name: str | None,
        model_name: str | None,
        allow_missing_supplier_prompt_fallback: bool = False,
    ) -> SupplierPromptResolution:
        norm_provider = _normalize_provider(provider_name)
        norm_model = _normalize_model(model_name)

        if norm_provider is None and norm_model is not None:
            return SupplierPromptResolution(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                client_id=None,
                client_supplier_id=None,
                provider_name=norm_provider,
                model_name=norm_model,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                editable_instructions=None,
                fallback_used=False,
                fallback_reason=None,
                resolution_status="error",
                warnings=(),
                error_code=SupplierPromptResolutionErrorCode.INVALID_SCOPE_INPUT,
            )

        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            return SupplierPromptResolution(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                client_id=None,
                client_supplier_id=None,
                provider_name=norm_provider,
                model_name=norm_model,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                editable_instructions=None,
                fallback_used=False,
                fallback_reason=None,
                resolution_status="error",
                warnings=(),
                error_code=SupplierPromptResolutionErrorCode.INVENTORY_NOT_FOUND,
            )

        if inventory.client_id is None or not str(inventory.client_id).strip():
            return SupplierPromptResolution(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                client_id=None,
                client_supplier_id=None,
                provider_name=norm_provider,
                model_name=norm_model,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                editable_instructions=None,
                fallback_used=True,
                fallback_reason=SupplierPromptFallbackReason.INVENTORY_WITHOUT_CLIENT,
                resolution_status="fallback",
            )

        client_id = str(inventory.client_id).strip()

        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            return SupplierPromptResolution(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                client_id=client_id,
                client_supplier_id=None,
                provider_name=norm_provider,
                model_name=norm_model,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                editable_instructions=None,
                fallback_used=False,
                fallback_reason=None,
                resolution_status="error",
                warnings=(),
                error_code=SupplierPromptResolutionErrorCode.AISLE_NOT_FOUND,
            )

        if aisle.inventory_id != inventory_id:
            return SupplierPromptResolution(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                client_id=client_id,
                client_supplier_id=None,
                provider_name=norm_provider,
                model_name=norm_model,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                editable_instructions=None,
                fallback_used=False,
                fallback_reason=None,
                resolution_status="error",
                warnings=(),
                error_code=SupplierPromptResolutionErrorCode.AISLE_INVENTORY_MISMATCH,
            )

        if aisle.client_supplier_id is None or not str(aisle.client_supplier_id).strip():
            return SupplierPromptResolution(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                client_id=client_id,
                client_supplier_id=None,
                provider_name=norm_provider,
                model_name=norm_model,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                editable_instructions=None,
                fallback_used=True,
                fallback_reason=SupplierPromptFallbackReason.AISLE_WITHOUT_CLIENT_SUPPLIER,
                resolution_status="fallback",
            )

        client_supplier_id = str(aisle.client_supplier_id).strip()
        supplier = self._client_supplier_repo.get_by_id(client_supplier_id)
        if supplier is None:
            return SupplierPromptResolution(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                client_id=client_id,
                client_supplier_id=client_supplier_id,
                provider_name=norm_provider,
                model_name=norm_model,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                editable_instructions=None,
                fallback_used=False,
                fallback_reason=None,
                resolution_status="error",
                warnings=(),
                error_code=SupplierPromptResolutionErrorCode.CLIENT_SUPPLIER_NOT_FOUND,
            )

        supplier_client_id = str(supplier.client_id).strip()
        if supplier_client_id != client_id:
            return SupplierPromptResolution(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                client_id=client_id,
                client_supplier_id=client_supplier_id,
                provider_name=norm_provider,
                model_name=norm_model,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                editable_instructions=None,
                fallback_used=False,
                fallback_reason=None,
                resolution_status="error",
                warnings=(),
                error_code=SupplierPromptResolutionErrorCode.CLIENT_SUPPLIER_OWNERSHIP_MISMATCH,
            )

        active = _resolve_active_with_precedence(
            self._supplier_prompt_config_repo,
            client_supplier_id,
            norm_provider,
            norm_model,
        )
        if active is None:
            if allow_missing_supplier_prompt_fallback:
                return SupplierPromptResolution(
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                    client_id=client_id,
                    client_supplier_id=client_supplier_id,
                    provider_name=norm_provider,
                    model_name=norm_model,
                    supplier_prompt_config_id=None,
                    supplier_prompt_config_version=None,
                    editable_instructions=None,
                    fallback_used=True,
                    fallback_reason=SupplierPromptFallbackReason.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG,
                    resolution_status="fallback",
                )
            return SupplierPromptResolution(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                client_id=client_id,
                client_supplier_id=client_supplier_id,
                provider_name=norm_provider,
                model_name=norm_model,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                editable_instructions=None,
                fallback_used=False,
                fallback_reason=None,
                resolution_status="error",
                warnings=(),
                error_code=SupplierPromptResolutionErrorCode.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG,
            )

        return SupplierPromptResolution(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            client_id=client_id,
            client_supplier_id=client_supplier_id,
            provider_name=norm_provider,
            model_name=norm_model,
            supplier_prompt_config_id=active.id,
            supplier_prompt_config_version=int(active.version),
            editable_instructions=active.instructions_text,
            fallback_used=False,
            fallback_reason=None,
            resolution_status="resolved",
        )
