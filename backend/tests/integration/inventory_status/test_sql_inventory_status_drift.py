"""SQL Server integration: inventory status drift detect / repair / concurrency."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

import pytest

from src.application.services.inventory_status_reconciler import (
    InventoryStatusReconciler,
    InventoryStatusRepairOutcome,
)
from src.application.use_cases.inventories.backfill_inventory_statuses import (
    BackfillInventoryStatusesUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.derive_status_from_aisles import derive_inventory_status_from_aisles
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


def _fresh_client(sql_client):
    return type(sql_client)(sql_client.connection_string)


def _seed(client, *, aisle_status: AisleStatus = AisleStatus.COMPLETED) -> tuple[str, str]:
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
            status=aisle_status,
            created_at=now,
            updated_at=now,
        )
    )
    return inv_id, aisle_id


def test_sql_detect_and_repair_idempotent(sql_client) -> None:
    inv_id, _aisle_id = _seed(sql_client)
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock())

    drift = reconciler.detect(inv_id)
    assert drift is not None
    assert drift.stored_status == InventoryStatus.DRAFT.value
    assert drift.expected_status == InventoryStatus.COMPLETED.value
    assert inv_repo.get_by_id(inv_id).status == InventoryStatus.DRAFT

    repaired = reconciler.repair(inv_id)
    assert repaired.outcome == InventoryStatusRepairOutcome.REPAIRED
    inv = inv_repo.get_by_id(inv_id)
    assert inv is not None
    assert inv.status == InventoryStatus.COMPLETED
    assert inv.completed_at is not None

    assert reconciler.detect(inv_id) is None
    assert reconciler.repair(inv_id).outcome == InventoryStatusRepairOutcome.CONSISTENT
    assert reconciler.reconcile(inv_id) is False


def test_sql_concurrent_repair_converges(sql_client) -> None:
    inv_id, _aisle_id = _seed(sql_client)
    start = threading.Barrier(2)
    results: list[InventoryStatusRepairOutcome] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def run(client) -> None:
        try:
            r = InventoryStatusReconciler(
                SqlInventoryRepository(client),
                SqlAisleRepository(client),
                FixedClock(),
            )
            start.wait(timeout=30)
            outcome = r.repair(inv_id).outcome
            with lock:
                results.append(outcome)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    c1 = _fresh_client(sql_client)
    c2 = _fresh_client(sql_client)
    t1 = threading.Thread(target=run, args=(c1,))
    t2 = threading.Thread(target=run, args=(c2,))
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)
    assert not t1.is_alive()
    assert not t2.is_alive()
    assert not errors

    repaired = sum(1 for o in results if o == InventoryStatusRepairOutcome.REPAIRED)
    peers = [
        o
        for o in results
        if o
        in (
            InventoryStatusRepairOutcome.CONSISTENT,
            InventoryStatusRepairOutcome.CAS_MISS,
            InventoryStatusRepairOutcome.RETRY_EXHAUSTED,
        )
    ]
    assert repaired == 1, results
    assert len(peers) == 1, results

    fresh = SqlInventoryRepository(_fresh_client(sql_client))
    aisle_fresh = SqlAisleRepository(_fresh_client(sql_client))
    inv = fresh.get_by_id(inv_id)
    assert inv is not None
    assert inv.status == InventoryStatus.COMPLETED
    assert inv.completed_at is not None
    derived = derive_inventory_status_from_aisles(aisle_fresh.list_by_inventory(inv_id))
    assert inv.status == derived


def _race_aisle_mutation(
    sql_client,
    *,
    worker_aisle_status: AisleStatus,
    expected_inventory_status: InventoryStatus,
) -> None:
    inv_id, aisle_id = _seed(sql_client, aisle_status=AisleStatus.COMPLETED)
    ready_to_mutate = threading.Event()
    mutate_done = threading.Event()
    errors: list[BaseException] = []
    repair_outcome: list[InventoryStatusRepairOutcome] = []

    def before_cas() -> None:
        ready_to_mutate.set()
        assert mutate_done.wait(timeout=30), "worker did not mutate aisle in time"

    def repair_thread() -> None:
        try:
            client = _fresh_client(sql_client)
            r = InventoryStatusReconciler(
                SqlInventoryRepository(client),
                SqlAisleRepository(client),
                FixedClock(),
                max_attempts=3,
                before_cas_hook=before_cas,
            )
            repair_outcome.append(r.repair(inv_id).outcome)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def worker_thread() -> None:
        try:
            assert ready_to_mutate.wait(timeout=30), "repair did not reach pre-CAS"
            client = _fresh_client(sql_client)
            aisle_repo = SqlAisleRepository(client)
            aisle = aisle_repo.get_by_id(aisle_id)
            assert aisle is not None
            aisle.status = worker_aisle_status
            aisle.updated_at = datetime.now(timezone.utc)
            aisle_repo.save(aisle)
            mutate_done.set()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            mutate_done.set()

    t_repair = threading.Thread(target=repair_thread)
    t_worker = threading.Thread(target=worker_thread)
    t_repair.start()
    t_worker.start()
    t_repair.join(timeout=60)
    t_worker.join(timeout=60)
    assert not t_repair.is_alive()
    assert not t_worker.is_alive()
    assert not errors
    assert repair_outcome
    assert repair_outcome[0] in (
        InventoryStatusRepairOutcome.REPAIRED,
        InventoryStatusRepairOutcome.CONSISTENT,
    )

    fresh_inv = SqlInventoryRepository(_fresh_client(sql_client)).get_by_id(inv_id)
    fresh_aisles = list(
        SqlAisleRepository(_fresh_client(sql_client)).list_by_inventory(inv_id)
    )
    assert fresh_inv is not None
    assert fresh_inv.status == expected_inventory_status
    assert fresh_inv.status == derive_inventory_status_from_aisles(fresh_aisles)
    assert fresh_inv.completed_at is None
    detect = InventoryStatusReconciler(
        SqlInventoryRepository(_fresh_client(sql_client)),
        SqlAisleRepository(_fresh_client(sql_client)),
        FixedClock(),
    ).detect(inv_id)
    assert detect is None


def test_sql_reconciler_vs_aisle_processing(sql_client) -> None:
    _race_aisle_mutation(
        sql_client,
        worker_aisle_status=AisleStatus.PROCESSING,
        expected_inventory_status=InventoryStatus.PROCESSING,
    )


def test_sql_reconciler_vs_aisle_failed(sql_client) -> None:
    _race_aisle_mutation(
        sql_client,
        worker_aisle_status=AisleStatus.FAILED,
        expected_inventory_status=InventoryStatus.FAILED,
    )


def test_sql_backfill_detect_only_zero_writes(sql_client) -> None:
    inv_id, _aisle_id = _seed(sql_client)
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    before = inv_repo.get_by_id(inv_id)
    assert before is not None
    stamp_updated = before.updated_at
    stamp_completed = before.completed_at
    stamp_status = before.status

    uc = BackfillInventoryStatusesUseCase(
        inv_repo,
        InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock()),
    )
    result = uc.execute(detect_only=True)
    assert result.inventories_drifted >= 1
    assert result.inventories_updated == 0
    assert any(d.entity_id == inv_id for d in result.drifts)

    fresh = SqlInventoryRepository(_fresh_client(sql_client)).get_by_id(inv_id)
    assert fresh is not None
    assert fresh.status == stamp_status
    assert fresh.updated_at == stamp_updated
    assert fresh.completed_at == stamp_completed


def test_sql_backfill_repair_then_idempotent(sql_client) -> None:
    inv_id, _aisle_id = _seed(sql_client)
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    uc = BackfillInventoryStatusesUseCase(
        inv_repo,
        InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock()),
    )
    first = uc.execute(detect_only=False)
    assert first.inventories_updated >= 1
    assert any(d.entity_id == inv_id for d in first.drifts)

    second = uc.execute(detect_only=False)
    assert second.inventories_updated == 0

    fresh = SqlInventoryRepository(_fresh_client(sql_client)).get_by_id(inv_id)
    aisles = list(SqlAisleRepository(_fresh_client(sql_client)).list_by_inventory(inv_id))
    assert fresh is not None
    assert fresh.status == InventoryStatus.COMPLETED
    assert fresh.completed_at is not None
    assert fresh.status == derive_inventory_status_from_aisles(aisles)
