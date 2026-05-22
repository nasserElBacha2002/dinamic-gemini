"""A5 legacy/default client+supplier backfill use case (idempotent, explicit run)."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    ClientSupplierRepository,
    InventoryRepository,
)
from src.domain.aisle.entities import Aisle
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.inventory.entities import Inventory

LEGACY_DEFAULT_CLIENT_NAME = "Legacy Default"
LEGACY_DEFAULT_SUPPLIER_NAME = "Legacy Default Supplier"
LEGACY_DEFAULT_CLIENT_ID = "00000000-0000-0000-0000-000000000001"
LEGACY_DEFAULT_SUPPLIER_ID = "00000000-0000-0000-0000-000000000002"


@dataclass
class BackfillLegacyClientSupplierDefaultsResult:
    legacy_client_id: str
    legacy_supplier_id: str
    legacy_client_created: bool
    legacy_supplier_created: bool
    inventories_null_before: int
    inventories_updated: int
    inventories_null_after: int
    aisles_null_before: int
    aisles_updated: int
    aisles_null_after: int


class BackfillLegacyClientSupplierDefaultsUseCase:
    """Ensure canonical legacy records and assign NULL inventory/aisle links.

    Idempotent behavior:
    - Reuses existing legacy client/supplier records when present.
    - Only updates NULL `inventories.client_id` and NULL `aisles.client_supplier_id`.
    - Never overwrites non-NULL values.
    """

    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        clock: Clock,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._clock = clock

    def execute(self) -> BackfillLegacyClientSupplierDefaultsResult:
        legacy_client, legacy_client_created = self._ensure_legacy_client()
        legacy_supplier, legacy_supplier_created = self._ensure_legacy_supplier(legacy_client.id)

        inventories: list[Inventory] = list(self._inventory_repo.list_all())
        inventories_null_before = sum(1 for inv in inventories if inv.client_id is None)
        inventories_updated = 0
        for inventory in inventories:
            if inventory.client_id is not None:
                continue
            inventory.client_id = legacy_client.id
            inventory.updated_at = self._clock.now()
            self._inventory_repo.save(inventory)
            inventories_updated += 1

        aisles: list[Aisle] = []
        for inventory in inventories:
            aisles.extend(self._aisle_repo.list_by_inventory(inventory.id))
        aisles_null_before = sum(1 for aisle in aisles if aisle.client_supplier_id is None)
        aisles_updated = 0
        for aisle in aisles:
            if aisle.client_supplier_id is not None:
                continue
            aisle.client_supplier_id = legacy_supplier.id
            aisle.updated_at = self._clock.now()
            self._aisle_repo.save(aisle)
            aisles_updated += 1

        inventories_after: list[Inventory] = list(self._inventory_repo.list_all())
        inventories_null_after = sum(1 for inv in inventories_after if inv.client_id is None)
        aisles_after: list[Aisle] = []
        for inventory in inventories_after:
            aisles_after.extend(self._aisle_repo.list_by_inventory(inventory.id))
        aisles_null_after = sum(1 for aisle in aisles_after if aisle.client_supplier_id is None)

        return BackfillLegacyClientSupplierDefaultsResult(
            legacy_client_id=legacy_client.id,
            legacy_supplier_id=legacy_supplier.id,
            legacy_client_created=legacy_client_created,
            legacy_supplier_created=legacy_supplier_created,
            inventories_null_before=inventories_null_before,
            inventories_updated=inventories_updated,
            inventories_null_after=inventories_null_after,
            aisles_null_before=aisles_null_before,
            aisles_updated=aisles_updated,
            aisles_null_after=aisles_null_after,
        )

    def _ensure_legacy_client(self) -> tuple[Client, bool]:
        by_id = self._client_repo.get_by_id(LEGACY_DEFAULT_CLIENT_ID)
        if by_id is not None:
            return by_id, False

        same_name = [
            c
            for c in self._client_repo.list_all()
            if (c.name or "").strip().lower() == LEGACY_DEFAULT_CLIENT_NAME.lower()
        ]
        if same_name:
            same_name.sort(key=lambda c: (c.created_at, c.id))
            return same_name[0], False

        now = self._clock.now()
        created = Client(
            id=LEGACY_DEFAULT_CLIENT_ID,
            name=LEGACY_DEFAULT_CLIENT_NAME,
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self._client_repo.save(created)
        return created, True

    def _ensure_legacy_supplier(self, legacy_client_id: str) -> tuple[ClientSupplier, bool]:
        by_id = self._client_supplier_repo.get_by_id(LEGACY_DEFAULT_SUPPLIER_ID)
        if by_id is not None:
            if by_id.client_id != legacy_client_id:
                raise ValueError(
                    "Legacy supplier id exists but belongs to a different client_id; "
                    "resolve conflicting record before running backfill"
                )
            return by_id, False

        by_name = self._client_supplier_repo.get_by_client_and_name(
            legacy_client_id, LEGACY_DEFAULT_SUPPLIER_NAME
        )
        if by_name is not None:
            return by_name, False

        now = self._clock.now()
        created = ClientSupplier(
            id=LEGACY_DEFAULT_SUPPLIER_ID,
            client_id=legacy_client_id,
            name=LEGACY_DEFAULT_SUPPLIER_NAME,
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self._client_supplier_repo.save(created)
        return created, True

