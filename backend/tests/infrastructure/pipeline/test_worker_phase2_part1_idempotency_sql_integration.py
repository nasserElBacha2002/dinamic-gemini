"""Phase 2 Part 1 — SQL Server position-layer idempotency (P2-T001-SQL-POSITIONS)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultCommand
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.persistence.sql_job_result_unit_of_work import SqlJobResultUnitOfWorkFactory
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository
from src.infrastructure.repositories.sql_final_count_repository import SqlFinalCountRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_normalized_label_repository import (
    SqlNormalizedLabelRepository,
)
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_product_record_repository import (
    SqlProductRecordRepository,
)
from src.infrastructure.repositories.sql_raw_label_repository import SqlRawLabelRepository
from tests.support.worker_phase1.executor_harness import FixedClock, make_two_entity_hybrid_report
from tests.support.worker_phase1.sql_cleanup import (
    assert_sql_integration_database_is_safe,
    cleanup_worker_phase1_sql_scope,
)
from tests.support.worker_phase2.duplicate_detection import duplicate_positions_by_job_entity_uid
from tests.support.worker_phase2.persist_builders import build_persist_aisle_result_use_case
from tests.support.worker_phase2.sql_verification import verify_sql_scope_fully_removed


@pytest.fixture
def sql_client_or_skip():
    from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
    from tests.support.sql_integration import sql_server_client_or_skip

    try:
        assert_sql_integration_database_is_safe()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    try:
        import pyodbc  # noqa: F401
    except ImportError:
        pytest.skip("pyodbc required for SQL Server integration")
    return sql_server_client_or_skip(resolve_sqlserver_connection_config().connection_string)


def test_p2_t001_sql_positions_same_job_identical_persist_is_idempotent(
    sql_client_or_skip,
) -> None:
    """P2-T001-SQL-POSITIONS: SQL position rows stay stable on identical re-persist after Part 2."""
    client = sql_client_or_skip
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:12]
    inv_id = f"inv-p2-{suffix}"
    aisle_id = f"aisle-p2-{suffix}"
    job_id = f"job-p2-{suffix}"

    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    pos_repo = SqlPositionRepository(client)
    prod_repo = SqlProductRecordRepository(client)
    ev_repo = SqlEvidenceRepository(client)
    raw_repo = SqlRawLabelRepository(client)
    norm_repo = SqlNormalizedLabelRepository(client)
    final_repo = SqlFinalCountRepository(client)

    try:
        inv_repo.save(Inventory(inv_id, "P2 SQL", InventoryStatus.PROCESSING, now, now))
        aisle_repo.save(Aisle(aisle_id, inv_id, "P2", AisleStatus.PROCESSING, now, now))

        persist = build_persist_aisle_result_use_case(
            position_repo=pos_repo,
            product_record_repo=prod_repo,
            evidence_repo=ev_repo,
            aisle_repo=aisle_repo,
            raw_label_repo=raw_repo,
            normalized_label_repo=norm_repo,
            final_count_repo=final_repo,
            clock=FixedClock(now),
            job_result_uow_factory=SqlJobResultUnitOfWorkFactory(client),
        )
        report = make_two_entity_hybrid_report()
        cmd = PersistAisleResultCommand(
            aisle_id=aisle_id,
            job_id=job_id,
            report=report,
            run_dir=Path("/tmp/p2-sql"),
            run_id="run",
        )

        persist.execute(cmd)
        after_first = list(pos_repo.list_by_aisle(aisle_id, job_id=job_id))
        assert len(after_first) == 2

        persist.execute(cmd)
        after_second = list(pos_repo.list_by_aisle(aisle_id, job_id=job_id))
        assert len(after_second) == 2
        assert duplicate_positions_by_job_entity_uid(after_second) == {}

        persist.execute(cmd)
        after_third = list(pos_repo.list_by_aisle(aisle_id, job_id=job_id))
        assert len(after_third) == 2
    finally:
        cleanup_worker_phase1_sql_scope(
            client,
            inventory_id=inv_id,
            aisle_id=aisle_id,
            job_id=job_id,
        )
        verify_sql_scope_fully_removed(
            client,
            inventory_repo=inv_repo,
            aisle_repo=aisle_repo,
            position_repo=pos_repo,
            inventory_id=inv_id,
            aisle_id=aisle_id,
            job_id=job_id,
        )
