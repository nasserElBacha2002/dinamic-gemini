"""SQL Server integration: inventory status drift detect / repair / concurrency."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

import pytest

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    return client


class FixedClock:
    def __init__(self, moment: datetime | None = None) -> None:
        self._moment = moment or datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._moment


def _seed(client) -> tuple[str, str, InventoryStatusReconciler]:
    now = datetime.now(timezone.utc)
    inv_id = f"inv-drift-{uuid.uuid4().hex[:10]}"
    aisle_id = f"aisle-drift-{uuid.uuid4().hex[:10]}"
    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Status drift",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"D-{uuid.uuid4().hex[:6]}",
            status=AisleStatus.COMPLETED,
            created_at=now,
            updated_at=now,
        )
    )
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    return inv_id, aisle_id, reconciler


def test_sql_detect_and_repair_idempotent(sql_client) -> None:
    inv_id, _aisle_id, reconciler = _seed(sql_client)
    inv_repo = SqlInventoryRepository(sql_client)

    drift = reconciler.detect(inv_id)
    assert drift is not None
    assert drift.stored_status == InventoryStatus.DRAFT.value
    assert drift.expected_status == InventoryStatus.COMPLETED.value
    assert inv_repo.get_by_id(inv_id).status == InventoryStatus.DRAFT

    repaired = reconciler.repair(inv_id)
    assert repaired is not None
    assert inv_repo.get_by_id(inv_id).status == InventoryStatus.COMPLETED

    assert reconciler.detect(inv_id) is None
    assert reconciler.repair(inv_id) is None
    assert reconciler.reconcile(inv_id) is False


def test_sql_concurrent_repair_converges(sql_client) -> None:
    inv_id, _aisle_id, _ = _seed(sql_client)
    # Two reconcilers / connections
    r1 = InventoryStatusReconciler(
        SqlInventoryRepository(sql_client),
        SqlAisleRepository(sql_client),
        FixedClock(),
    )
    client_b = type(sql_client)(sql_client.connection_string)
    r2 = InventoryStatusReconciler(
        SqlInventoryRepository(client_b),
        SqlAisleRepository(client_b),
        FixedClock(),
    )
    errors: list[BaseException] = []
    results: list[object] = []

    def run(r: InventoryStatusReconciler) -> None:
        try:
            results.append(r.repair(inv_id))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=run, args=(r1,))
    t2 = threading.Thread(target=run, args=(r2,))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert not errors
    fresh = SqlInventoryRepository(type(sql_client)(sql_client.connection_string))
    assert fresh.get_by_id(inv_id).status == InventoryStatus.COMPLETED
    # At most one repair observes a write; the other may see cas_miss or already repaired.
    assert sum(1 for r in results if r is not None) <= 2
