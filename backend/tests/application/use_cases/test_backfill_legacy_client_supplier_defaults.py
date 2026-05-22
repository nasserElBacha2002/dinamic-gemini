"""Tests for A5 legacy/default client+supplier backfill."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.use_cases.suppliers.backfill_legacy_client_supplier_defaults import (
    LEGACY_DEFAULT_CLIENT_NAME,
    LEGACY_DEFAULT_SUPPLIER_NAME,
    BackfillLegacyClientSupplierDefaultsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _build_uc(
    *,
    client_repo: MemoryClientRepository | None = None,
    supplier_repo: MemoryClientSupplierRepository | None = None,
    inventory_repo: MemoryInventoryRepository | None = None,
    aisle_repo: MemoryAisleRepository | None = None,
    now: datetime | None = None,
) -> BackfillLegacyClientSupplierDefaultsUseCase:
    return BackfillLegacyClientSupplierDefaultsUseCase(
        client_repo=client_repo or MemoryClientRepository(),
        client_supplier_repo=supplier_repo or MemoryClientSupplierRepository(),
        inventory_repo=inventory_repo or MemoryInventoryRepository(),
        aisle_repo=aisle_repo or MemoryAisleRepository(),
        clock=FixedClock(now or datetime(2026, 5, 1, tzinfo=timezone.utc)),
    )


def test_first_run_creates_legacy_records_and_backfills_null_links() -> None:
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    client_repo = MemoryClientRepository()
    supplier_repo = MemoryClientSupplierRepository()

    inv_repo.save(Inventory("inv-1", "Inventory 1", InventoryStatus.DRAFT, now, now, client_id=None))
    inv_repo.save(Inventory("inv-2", "Inventory 2", InventoryStatus.DRAFT, now, now, client_id=None))
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A-1", AisleStatus.CREATED, now, now))
    aisle_repo.save(Aisle("aisle-2", "inv-2", "A-2", AisleStatus.CREATED, now, now))

    result = _build_uc(
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        now=now,
    ).execute()

    assert result.legacy_client_created is True
    assert result.legacy_supplier_created is True
    assert result.inventories_null_before == 2
    assert result.inventories_updated == 2
    assert result.inventories_null_after == 0
    assert result.aisles_null_before == 2
    assert result.aisles_updated == 2
    assert result.aisles_null_after == 0

    legacy_client = client_repo.get_by_id(result.legacy_client_id)
    assert legacy_client is not None
    assert legacy_client.name == LEGACY_DEFAULT_CLIENT_NAME
    legacy_supplier = supplier_repo.get_by_id(result.legacy_supplier_id)
    assert legacy_supplier is not None
    assert legacy_supplier.name == LEGACY_DEFAULT_SUPPLIER_NAME
    assert legacy_supplier.client_id == legacy_client.id


def test_second_run_is_idempotent_and_does_not_duplicate_or_overwrite_non_null() -> None:
    now = datetime(2026, 5, 2, tzinfo=timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    client_repo = MemoryClientRepository()
    supplier_repo = MemoryClientSupplierRepository()

    client_repo.save(
        Client(
            id="client-custom",
            name="Custom Client",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    supplier_repo.save(
        ClientSupplier(
            id="supplier-custom",
            client_id="client-custom",
            name="Custom Supplier",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )

    inv_repo.save(
        Inventory(
            "inv-null",
            "Inventory Null",
            InventoryStatus.DRAFT,
            now,
            now,
            client_id=None,
        )
    )
    inv_repo.save(
        Inventory(
            "inv-set",
            "Inventory Set",
            InventoryStatus.DRAFT,
            now,
            now,
            client_id="client-custom",
        )
    )
    aisle_repo.save(Aisle("aisle-null", "inv-null", "AN", AisleStatus.CREATED, now, now))
    aisle_repo.save(
        Aisle(
            "aisle-set",
            "inv-set",
            "AS",
            AisleStatus.CREATED,
            now,
            now,
            client_supplier_id="supplier-custom",
        )
    )

    uc = _build_uc(
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        now=now,
    )
    first = uc.execute()
    second = uc.execute()

    assert first.inventories_updated == 1
    assert first.aisles_updated == 1
    assert second.legacy_client_created is False
    assert second.legacy_supplier_created is False
    assert second.inventories_updated == 0
    assert second.aisles_updated == 0
    assert inv_repo.get_by_id("inv-set").client_id == "client-custom"
    assert aisle_repo.get_by_id("aisle-set").client_supplier_id == "supplier-custom"


def test_zero_inventories_and_aisles_is_safe_and_reports_zeroes() -> None:
    result = _build_uc().execute()
    assert result.inventories_null_before == 0
    assert result.inventories_updated == 0
    assert result.inventories_null_after == 0
    assert result.aisles_null_before == 0
    assert result.aisles_updated == 0
    assert result.aisles_null_after == 0


def test_existing_legacy_name_records_are_reused() -> None:
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)
    client_repo = MemoryClientRepository()
    supplier_repo = MemoryClientSupplierRepository()
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()

    client_repo.save(
        Client(
            id="legacy-by-name",
            name=LEGACY_DEFAULT_CLIENT_NAME,
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    supplier_repo.save(
        ClientSupplier(
            id="legacy-supplier-by-name",
            client_id="legacy-by-name",
            name=LEGACY_DEFAULT_SUPPLIER_NAME,
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    inv_repo.save(Inventory("inv-1", "Inventory", InventoryStatus.DRAFT, now, now, client_id=None))
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A-1", AisleStatus.CREATED, now, now))

    result = _build_uc(
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        now=now,
    ).execute()

    assert result.legacy_client_created is False
    assert result.legacy_supplier_created is False
    assert result.legacy_client_id == "legacy-by-name"
    assert result.legacy_supplier_id == "legacy-supplier-by-name"
    assert inv_repo.get_by_id("inv-1").client_id == "legacy-by-name"
    assert aisle_repo.get_by_id("aisle-1").client_supplier_id == "legacy-supplier-by-name"


def test_fails_loudly_when_legacy_supplier_id_belongs_to_another_client() -> None:
    now = datetime(2026, 5, 4, tzinfo=timezone.utc)
    client_repo = MemoryClientRepository()
    supplier_repo = MemoryClientSupplierRepository()
    client_repo.save(
        Client(
            id="legacy-client-canonical",
            name=LEGACY_DEFAULT_CLIENT_NAME,
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    supplier_repo.save(
        ClientSupplier(
            id="00000000-0000-0000-0000-000000000002",
            client_id="different-client",
            name="Any Supplier",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )

    uc = _build_uc(
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        inventory_repo=MemoryInventoryRepository(),
        aisle_repo=MemoryAisleRepository(),
        now=now,
    )
    with pytest.raises(ValueError, match="belongs to a different client_id"):
        uc.execute()

