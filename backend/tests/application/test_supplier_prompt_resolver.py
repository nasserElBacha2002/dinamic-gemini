"""Unit tests for ``SupplierPromptResolver`` — Phase E2."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.supplier_prompt_resolver import (
    SupplierPromptFallbackReason,
    SupplierPromptResolutionErrorCode,
    SupplierPromptResolver,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_supplier_prompt_config_repository import (
    MemorySupplierPromptConfigRepository,
)


def _dt() -> datetime:
    return datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)


def _inv(
    *,
    inv_id: str = "inv-1",
    client_id: str | None = "client-1",
) -> Inventory:
    now = _dt()
    return Inventory(
        id=inv_id,
        name="Test",
        status=InventoryStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        client_id=client_id,
    )


def _aisle(
    *,
    aisle_id: str = "aisle-1",
    inventory_id: str = "inv-1",
    client_supplier_id: str | None = "sup-1",
) -> Aisle:
    now = _dt()
    return Aisle(
        id=aisle_id,
        inventory_id=inventory_id,
        code="A1",
        status=AisleStatus.QUEUED,
        created_at=now,
        updated_at=now,
        client_supplier_id=client_supplier_id,
    )


def _supplier(
    *,
    sup_id: str = "sup-1",
    client_id: str = "client-1",
) -> ClientSupplier:
    now = _dt()
    return ClientSupplier(
        id=sup_id,
        client_id=client_id,
        name="S",
        status=ClientSupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _cfg(
    *,
    cid: str = "cfg-1",
    client_supplier_id: str = "sup-1",
    provider_name: str | None,
    model_name: str | None,
    text: str = "hello",
    version: int = 1,
    active: bool = True,
) -> SupplierPromptConfig:
    now = _dt()
    return SupplierPromptConfig(
        id=cid,
        client_supplier_id=client_supplier_id,
        provider_name=provider_name,
        model_name=model_name,
        instructions_text=text,
        version=version,
        is_active=active,
        created_at=now,
        updated_at=now,
    )


def _resolver(
    inv: MemoryInventoryRepository | None = None,
    aisle: MemoryAisleRepository | None = None,
    sup: MemoryClientSupplierRepository | None = None,
    prompt: MemorySupplierPromptConfigRepository | None = None,
) -> SupplierPromptResolver:
    return SupplierPromptResolver(
        inventory_repo=inv or MemoryInventoryRepository(),
        aisle_repo=aisle or MemoryAisleRepository(),
        client_supplier_repo=sup or MemoryClientSupplierRepository(),
        supplier_prompt_config_repo=prompt or MemorySupplierPromptConfigRepository(),
    )


def test_resolves_exact_provider_and_model() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle())
    sup_r.save(_supplier())
    prompt_r.create(_cfg(cid="c1", provider_name="gemini", model_name="m1", text="exact"))
    prompt_r.create(_cfg(cid="c2", provider_name="gemini", model_name=None, text="prov-only"))

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name="m1",
    )
    assert r.resolution_status == "resolved"
    assert r.fallback_used is False
    assert r.supplier_prompt_config_id == "c1"
    assert r.editable_instructions == "exact"


def test_falls_back_to_provider_default_when_model_missing() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle())
    sup_r.save(_supplier())
    prompt_r.create(_cfg(cid="c1", provider_name="gemini", model_name=None, text="prov-default"))

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name="unknown-model",
    )
    assert r.resolution_status == "resolved"
    assert r.supplier_prompt_config_id == "c1"
    assert r.editable_instructions == "prov-default"


def test_falls_back_to_all_provider_scope() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle())
    sup_r.save(_supplier())
    prompt_r.create(_cfg(cid="c-all", provider_name=None, model_name=None, text="all"))

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="openai",
        model_name="gpt-4o",
    )
    assert r.resolution_status == "resolved"
    assert r.supplier_prompt_config_id == "c-all"


def test_fallback_when_no_active_config() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle())
    sup_r.save(_supplier())

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "fallback"
    assert r.fallback_used is True
    assert r.fallback_reason == SupplierPromptFallbackReason.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG


def test_fallback_inventory_without_client() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv(client_id=None))
    aisle_r.save(_aisle())

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "fallback"
    assert r.fallback_reason == SupplierPromptFallbackReason.INVENTORY_WITHOUT_CLIENT


def test_fallback_aisle_without_client_supplier() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle(client_supplier_id=None))

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "fallback"
    assert r.fallback_reason == SupplierPromptFallbackReason.AISLE_WITHOUT_CLIENT_SUPPLIER


def test_error_client_supplier_ownership_mismatch() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv(client_id="client-1"))
    aisle_r.save(_aisle())
    sup_r.save(_supplier(sup_id="sup-1", client_id="client-other"))

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "error"
    assert r.error_code == SupplierPromptResolutionErrorCode.CLIENT_SUPPLIER_OWNERSHIP_MISMATCH


def test_ignores_inactive_config() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle())
    sup_r.save(_supplier())
    prompt_r.create(
        _cfg(cid="c-inact", provider_name="gemini", model_name=None, text="x", active=False)
    )

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "fallback"
    assert r.fallback_reason == SupplierPromptFallbackReason.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG


def test_model_name_whitespace_normalized() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle())
    sup_r.save(_supplier())
    prompt_r.create(_cfg(cid="c-exact", provider_name="gemini", model_name="m1", text="exact-model"))

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=" m1 ",
    )
    assert r.resolution_status == "resolved"
    assert r.supplier_prompt_config_id == "c-exact"
    assert r.model_name == "m1"


def test_provider_name_case_normalized() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle())
    sup_r.save(_supplier())
    prompt_r.create(_cfg(cid="c1", provider_name="gemini", model_name=None, text="lowercase"))

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="  GEMINI ",
        model_name=None,
    )
    assert r.resolution_status == "resolved"
    assert r.provider_name == "gemini"


def test_never_resolves_config_from_other_supplier() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle(client_supplier_id="sup-1"))
    sup_r.save(_supplier(sup_id="sup-1", client_id="client-1"))
    sup_r.save(_supplier(sup_id="sup-2", client_id="client-1"))
    prompt_r.create(
        _cfg(cid="c-other", client_supplier_id="sup-2", provider_name="gemini", model_name=None)
    )

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "fallback"
    assert r.supplier_prompt_config_id is None


def test_aisle_inventory_mismatch_error() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle(inventory_id="other-inv"))

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "error"
    assert r.error_code == SupplierPromptResolutionErrorCode.AISLE_INVENTORY_MISMATCH


def test_inventory_not_found_error() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="missing",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "error"
    assert r.error_code == SupplierPromptResolutionErrorCode.INVENTORY_NOT_FOUND


def test_aisle_not_found_error() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="missing-aisle",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "error"
    assert r.error_code == SupplierPromptResolutionErrorCode.AISLE_NOT_FOUND


def test_client_supplier_row_missing_error() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle(client_supplier_id="orphan-sup"))

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="gemini",
        model_name=None,
    )
    assert r.resolution_status == "error"
    assert r.error_code == SupplierPromptResolutionErrorCode.CLIENT_SUPPLIER_NOT_FOUND


def test_model_without_provider_error() -> None:
    inv_r, aisle_r, sup_r, prompt_r = (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryClientSupplierRepository(),
        MemorySupplierPromptConfigRepository(),
    )
    inv_r.save(_inv())
    aisle_r.save(_aisle())
    sup_r.save(_supplier())

    r = _resolver(inv_r, aisle_r, sup_r, prompt_r).resolve(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        provider_name="",
        model_name="m1",
    )
    assert r.resolution_status == "error"
    assert r.error_code == SupplierPromptResolutionErrorCode.INVALID_SCOPE_INPUT
