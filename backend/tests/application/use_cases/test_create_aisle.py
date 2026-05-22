"""Tests for CreateAisleUseCase."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.errors import (
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
    ClientSupplierRequiredForAisleError,
    DuplicateAisleCodeError,
    InventoryClientRequiredForAisleError,
    InventoryNotFoundError,
)
from src.application.ports.repositories import (
    AisleRepository,
    ClientSupplierRepository,
    InventoryRepository,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.inventory.entities import Inventory, InventoryStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventories: list[Inventory] | None = None) -> None:
        self._store = {i.id: i for i in (inventories or [])}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code.strip():
                return a
        return None


class StubClientSupplierRepo(ClientSupplierRepository):
    def __init__(self, suppliers: list[ClientSupplier] | None = None) -> None:
        self._store = {s.id: s for s in (suppliers or [])}

    def save(self, supplier: ClientSupplier) -> None:
        self._store[supplier.id] = supplier

    def get_by_id(self, supplier_id: str) -> ClientSupplier | None:
        return self._store.get(supplier_id)

    def get_by_client_and_name(self, client_id: str, name: str) -> ClientSupplier | None:
        normalized = name.strip().lower()
        for supplier in self._store.values():
            if supplier.client_id == client_id and supplier.name.strip().lower() == normalized:
                return supplier
        return None

    def list_by_client(self, client_id: str) -> Sequence[ClientSupplier]:
        return [supplier for supplier in self._store.values() if supplier.client_id == client_id]


def _inv(now: datetime, *, client_id: str | None = "client-1") -> Inventory:
    return Inventory(
        id="inv-1",
        name="Warehouse",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id=client_id,
    )


def _supplier(now: datetime, sid: str = "sup-1", cid: str = "client-1") -> ClientSupplier:
    return ClientSupplier(
        id=sid,
        client_id=cid,
        name="Supplier A",
        status=ClientSupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def test_create_aisle_persists_and_returns_entity() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = _inv(now)
    sup = _supplier(now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    clock = FixedClock(now)

    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=StubClientSupplierRepo([sup]),
        clock=clock,
        status_reconciler=reconciler,
    )
    result = use_case.execute(
        CreateAisleCommand(inventory_id="inv-1", code="A-01", client_supplier_id="sup-1")
    )

    assert result.inventory_id == "inv-1"
    assert result.code == "A-01"
    assert result.status == AisleStatus.CREATED
    assert result.created_at == now
    assert result.client_supplier_id == "sup-1"
    assert aisle_repo.get_by_id(result.id) == result
    assert len(aisle_repo.list_by_inventory("inv-1")) == 1
    updated_inv = inv_repo.get_by_id("inv-1")
    assert updated_inv is not None
    assert updated_inv.status != InventoryStatus.DRAFT


def test_create_aisle_raises_when_inventory_not_found() -> None:
    aisle_repo = StubAisleRepo()
    inv_repo = StubInventoryRepo([])
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=StubClientSupplierRepo(),
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(InventoryNotFoundError):
        use_case.execute(
            CreateAisleCommand(inventory_id="nonexistent", code="A-01", client_supplier_id="sup-1")
        )


def test_create_aisle_raises_when_duplicate_code() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = _inv(now)
    sup = _supplier(now)
    existing = Aisle("a1", "inv-1", "A-01", AisleStatus.CREATED, now, now, client_supplier_id="sup-1")
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    aisle_repo.save(existing)

    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=StubClientSupplierRepo([sup]),
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(DuplicateAisleCodeError):
        use_case.execute(
            CreateAisleCommand(inventory_id="inv-1", code="A-01", client_supplier_id="sup-1")
        )


def test_create_aisle_normalizes_code_for_duplicate_check_and_entity() -> None:
    """Code is normalized once; duplicate check and stored entity use same value."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = _inv(now)
    sup = _supplier(now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=StubClientSupplierRepo([sup]),
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    result = use_case.execute(
        CreateAisleCommand(inventory_id="inv-1", code=" A-01 ", client_supplier_id="sup-1")
    )
    assert result.code == "A-01"

    with pytest.raises(DuplicateAisleCodeError):
        use_case.execute(
            CreateAisleCommand(inventory_id="inv-1", code="A-01", client_supplier_id="sup-1")
        )


def test_create_aisle_without_supplier_raises_when_inventory_has_client() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = _inv(now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=StubClientSupplierRepo(),
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(ClientSupplierRequiredForAisleError):
        use_case.execute(CreateAisleCommand(inventory_id="inv-1", code="A-02", client_supplier_id=None))


def test_create_aisle_with_valid_supplier_persists_client_supplier_id() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = _inv(now)
    supplier = _supplier(now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    supplier_repo = StubClientSupplierRepo([supplier])
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    result = use_case.execute(
        CreateAisleCommand(inventory_id="inv-1", code="A-03", client_supplier_id="sup-1")
    )
    assert result.client_supplier_id == "sup-1"


def test_create_aisle_normalizes_client_supplier_id_before_lookup_and_persist() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = _inv(now)
    supplier = _supplier(now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    supplier_repo = StubClientSupplierRepo([supplier])
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    result = use_case.execute(
        CreateAisleCommand(inventory_id="inv-1", code="A-03-N", client_supplier_id=" sup-1 ")
    )
    assert result.client_supplier_id == "sup-1"


def test_create_aisle_with_missing_supplier_raises_not_found() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = _inv(now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=StubClientSupplierRepo(),
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(ClientSupplierNotFoundError):
        use_case.execute(
            CreateAisleCommand(inventory_id="inv-1", code="A-04", client_supplier_id="sup-x")
        )


def test_create_aisle_when_inventory_has_no_client_raises_inventory_client_required_for_aisle() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = _inv(now, client_id=None)
    supplier = _supplier(now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=StubClientSupplierRepo([supplier]),
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(InventoryClientRequiredForAisleError):
        use_case.execute(CreateAisleCommand(inventory_id="inv-1", code="A-05", client_supplier_id="sup-1"))


def test_create_aisle_with_supplier_from_other_client_raises_conflict() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = _inv(now, client_id="client-1")
    supplier = ClientSupplier(
        id="sup-1",
        client_id="client-2",
        name="Supplier B",
        status=ClientSupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=StubClientSupplierRepo([supplier]),
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(ClientSupplierClientMismatchError):
        use_case.execute(
            CreateAisleCommand(inventory_id="inv-1", code="A-06", client_supplier_id="sup-1")
        )
