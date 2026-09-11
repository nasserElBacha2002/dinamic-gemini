"""Real-SQL concurrency contract for canonical position materialization."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.services.position_materialization import (
    MaterializePositionCommand,
    MaterializePositionService,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.position_materialization import (
    PositionMaterializationStatus,
)
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
)
from src.infrastructure.persistence.sql_position_materialization_unit_of_work import (
    SqlPositionMaterializationUnitOfWork,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_client_repository import SqlClientRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


def test_concurrent_requests_create_one_canonical_location_without_deadlock() -> None:
    sql_client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(sql_client)
    now = datetime.now(timezone.utc)
    token = uuid4().hex
    client_id = str(uuid4())
    inventory_id = str(uuid4())
    aisle_id = str(uuid4())
    normalized_code = f"RACK-{token[:8]}"

    SqlClientRepository(sql_client).save(
        Client(
            id=client_id,
            name=f"Materialization {token}",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    SqlInventoryRepository(sql_client).save(
        Inventory(
            id=inventory_id,
            name=f"Materialization {token}",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            client_id=client_id,
        )
    )
    SqlAisleRepository(sql_client).save(
        Aisle(
            id=aisle_id,
            inventory_id=inventory_id,
            code=f"A-{token[:8]}",
            status=AisleStatus.PROCESSING,
            created_at=now,
            updated_at=now,
        )
    )

    def run(index: int):
        command = MaterializePositionCommand(
            recognition=CanonicalPositionRecognition(
                raw_code=f"raw {normalized_code}",
                normalized_code=normalized_code,
                source=PositionRecognitionSource.CODE_SCAN,
            ),
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            principal=AccessPrincipal(
                actor_id=f"worker-{index}",
                client_id=client_id,
                roles=frozenset({"operator"}),
                is_platform=False,
            ),
            idempotency_key=f"concurrent-{token}-{index}",
        )
        return MaterializePositionService(SqlPositionMaterializationUnitOfWork(sql_client)).execute(
            command
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, range(2)))

        assert {result.status for result in results} == {
            PositionMaterializationStatus.MATERIALIZED,
            PositionMaterializationStatus.REUSED,
        }
        assert all(result.idempotent_replay is False for result in results)
        assert len({result.location_id for result in results}) == 1
        with sql_client.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT_BIG(*) AS row_count, MIN(id) AS location_id
                FROM dbo.aisle_locations
                WHERE client_id = ? AND aisle_id = ? AND normalized_code = ?
                """,
                (client_id, aisle_id, normalized_code),
            )
            row = cursor.fetchone()
            assert int(row.row_count) == 1
            assert str(row.location_id) == results[0].location_id
    finally:
        with sql_client.cursor() as cursor:
            cursor.execute(
                "DELETE FROM dbo.position_materialization_requests WHERE inventory_id = ?",
                (inventory_id,),
            )
            cursor.execute(
                "DELETE FROM dbo.aisle_locations WHERE client_id = ? AND aisle_id = ?",
                (client_id, aisle_id),
            )
            cursor.execute("DELETE FROM dbo.aisles WHERE id = ?", (aisle_id,))
            cursor.execute("DELETE FROM dbo.inventories WHERE id = ?", (inventory_id,))
            cursor.execute("DELETE FROM dbo.clients WHERE id = ?", (client_id,))
