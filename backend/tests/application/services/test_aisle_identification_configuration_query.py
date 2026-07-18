"""AisleIdentificationConfigurationQuery — single source of truth for API fields."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.aisle_identification_configuration_query import (
    AisleIdentificationConfigurationQuery,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import (
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _build_query() -> tuple[
    AisleIdentificationConfigurationQuery,
    MemoryAisleRepository,
    MemoryInventoryRepository,
    MemoryClientRepository,
]:
    aisle_repo = MemoryAisleRepository()
    inv_repo = MemoryInventoryRepository()
    client_repo = MemoryClientRepository()
    return (
        AisleIdentificationConfigurationQuery(aisle_repo, inv_repo, client_repo),
        aisle_repo,
        inv_repo,
        client_repo,
    )


def test_query_client_inheritance_consistent_for_aisle_and_inventory() -> None:
    query, aisle_repo, inv_repo, client_repo = _build_query()
    now = _now()
    client = Client(
        id="c1",
        name="Acme",
        status=ClientStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        default_identification_mode=AisleIdentificationMode.CODE_SCAN,
    )
    client_repo.save(client)
    inv = Inventory(
        id="i1",
        name="Inv",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id="c1",
        identification_mode=None,
    )
    inv_repo.save(inv)
    aisle = Aisle(
        id="a1",
        inventory_id="i1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        identification_mode=None,
    )
    aisle_repo.save(aisle)

    aisle_cfg = query.for_aisle(aisle)
    inv_cfg = query.for_inventory(inv)
    assert aisle_cfg.effective_mode == AisleIdentificationMode.CODE_SCAN
    assert aisle_cfg.source == AisleIdentificationModeSource.CLIENT
    assert inv_cfg.effective_mode == AisleIdentificationMode.CODE_SCAN
    assert inv_cfg.source == AisleIdentificationModeSource.CLIENT
    # Same aisle loaded again yields identical effective fields (list vs status parity).
    again = query.for_aisle_id("a1")
    assert again is not None
    assert again.effective_mode == aisle_cfg.effective_mode
    assert again.source == aisle_cfg.source


def test_query_aisle_override_beats_inventory_and_client() -> None:
    query, aisle_repo, inv_repo, client_repo = _build_query()
    now = _now()
    client_repo.save(
        Client(
            id="c1",
            name="Acme",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            default_identification_mode=AisleIdentificationMode.CODE_SCAN,
        )
    )
    inv_repo.save(
        Inventory(
            id="i1",
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            client_id="c1",
            identification_mode=AisleIdentificationMode.INTERNAL_OCR,
        )
    )
    aisle = Aisle(
        id="a1",
        inventory_id="i1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        identification_mode=AisleIdentificationMode.LEGACY_LLM,
    )
    aisle_repo.save(aisle)
    cfg = query.for_aisle(aisle)
    assert cfg.effective_mode == AisleIdentificationMode.LEGACY_LLM
    assert cfg.source == AisleIdentificationModeSource.AISLE
    assert cfg.configured_mode == AisleIdentificationMode.LEGACY_LLM
