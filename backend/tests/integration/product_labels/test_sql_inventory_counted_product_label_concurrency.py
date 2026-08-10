"""SQL concurrency for aisle-scoped product-label claims (requires SQL Server)."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

import pytest

from src.application.ports.inventory_counted_product_label_repository import (
    InventoryCountedProductLabel,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.infrastructure.database.sql_transaction import SqlServerTransaction
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_counted_product_label_repository import (
    SqlInventoryCountedProductLabelRepository,
)
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture(scope="module")
def _require_counted_labels_table(sql_client):
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.tables
            WHERE name = 'inventory_counted_product_labels'
            """
        )
        if cur.fetchone() is None:
            pytest.skip(
                "inventory_counted_product_labels missing; apply migration 0088"
            )
        cur.execute(
            """
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
              AND name = N'aisle_id'
            """
        )
        if cur.fetchone() is None:
            pytest.skip(
                "aisle_id missing on inventory_counted_product_labels; apply migration 0095"
            )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(
    inventory_id: str, aisle_id: str, label_id: str, product_id: str
) -> InventoryCountedProductLabel:
    return InventoryCountedProductLabel(
        id=str(uuid.uuid4()),
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        label_id=label_id,
        first_product_record_id=product_id,
        first_source_asset_id=str(uuid.uuid4()),
        first_job_id=str(uuid.uuid4()),
        first_position_id=str(uuid.uuid4()),
        created_at=_now(),
    )


def _seed_inventory_and_aisle(sql_client) -> tuple[str, str]:
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    now = _now()
    inv_id = f"inv-icpl-{uuid.uuid4().hex[:10]}"
    aisle_id = f"aisle-icpl-{uuid.uuid4().hex[:10]}"
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="ICPL concurrency",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"A-{uuid.uuid4().hex[:6]}",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    return inv_id, aisle_id


def test_two_workers_claim_same_label_one_wins(
    sql_client, _require_counted_labels_table
) -> None:
    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    label_id = "A1B2C3D4E5"
    results: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker(pid: str) -> None:
        repo = SqlInventoryCountedProductLabelRepository(sql_client)
        barrier.wait()
        ok = repo.try_claim(_row(inventory_id, aisle_id, label_id, pid))
        with lock:
            results.append(ok)

    t1 = threading.Thread(target=worker, args=("p1",))
    t2 = threading.Thread(target=worker, args=("p2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert results.count(True) == 1
    assert results.count(False) == 1


def test_claim_rollback_restores_availability(
    sql_client, _require_counted_labels_table
) -> None:
    """Claim inside an explicit txn, rollback, then claim succeeds on a fresh connection."""
    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    label_id = "FGHJKMNPQR"
    product_id = "prod-rollback-1"

    with SqlServerTransaction(sql_client.connection_string) as tx:
        repo = SqlInventoryCountedProductLabelRepository(
            sql_client, connection=tx.connection
        )
        claimed = repo.try_claim(_row(inventory_id, aisle_id, label_id, product_id))
        assert claimed is True
        # Simulate failure before commit: leave uncommitted and roll back.
        tx.rollback()

    # After rollback the unique (aisle_id, label_id) must be free again.
    repo2 = SqlInventoryCountedProductLabelRepository(sql_client)
    assert repo2.get(aisle_id, label_id) is None
    assert repo2.try_claim(_row(inventory_id, aisle_id, label_id, "prod-rollback-2")) is True


def test_same_label_different_aisles_both_claim(
    sql_client, _require_counted_labels_table
) -> None:
    inventory_id, aisle_a = _seed_inventory_and_aisle(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    now = _now()
    aisle_b = f"aisle-icpl-b-{uuid.uuid4().hex[:10]}"
    aisle_repo.save(
        Aisle(
            id=aisle_b,
            inventory_id=inventory_id,
            code=f"B-{uuid.uuid4().hex[:6]}",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    label_id = "VWXYZ23456"
    repo = SqlInventoryCountedProductLabelRepository(sql_client)
    assert repo.try_claim(_row(inventory_id, aisle_a, label_id, "p-a")) is True
    assert repo.try_claim(_row(inventory_id, aisle_b, label_id, "p-b")) is True
