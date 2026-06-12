"""Phase 2 Part 1 — optional SQL Server idempotency characterization (P2-T001-SQL)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
from src.infrastructure.repositories.memory_final_count_repository import (
    MemoryFinalCountRepository,
)
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_product_record_repository import (
    SqlProductRecordRepository,
)
from tests.support.worker_phase1.duplicate_detection import duplicate_positions_by_job_entity_uid
from tests.support.worker_phase1.executor_harness import (
    FixedClock,
    build_recompute_use_case,
    make_two_entity_hybrid_report,
)
from tests.support.worker_phase1.sql_cleanup import (
    assert_sql_integration_database_is_safe,
    cleanup_worker_phase1_sql_scope,
)


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


def test_p2_t001_sql_same_job_identical_persist_duplicates_rows(sql_client_or_skip) -> None:
    """P2-T001-SQL: identical persist twice on SQL leaves duplicate positions (NON_IDEMPOTENT)."""
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
    raw_repo = MemoryRawLabelRepository()

    try:
        inv_repo.save(Inventory(inv_id, "P2 SQL", InventoryStatus.PROCESSING, now, now))
        aisle_repo.save(Aisle(aisle_id, inv_id, "P2", AisleStatus.PROCESSING, now, now))

        persist = PersistAisleResultUseCase(
            position_repo=pos_repo,
            product_record_repo=prod_repo,
            evidence_repo=ev_repo,
            clock=FixedClock(now),
            hybrid_mapper=default_map_hybrid_report_to_domain,
            aisle_repo=aisle_repo,
            raw_label_repo=raw_repo,
            recompute_consolidated_uc=build_recompute_use_case(
                raw_repo=raw_repo,
                norm_repo=MemoryNormalizedLabelRepository(),
                final_repo=MemoryFinalCountRepository(),
                product_repo=prod_repo,
                position_repo=pos_repo,
            ),
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
        assert len(after_second) == 4
        dup = duplicate_positions_by_job_entity_uid(after_second)
        assert dup.get((job_id, "e1")) == 2
        assert dup.get((job_id, "e2")) == 2

        persist.execute(cmd)
        after_third = list(pos_repo.list_by_aisle(aisle_id, job_id=job_id))
        assert len(after_third) == 6
    finally:
        cleanup_worker_phase1_sql_scope(
            client,
            inventory_id=inv_id,
            aisle_id=aisle_id,
            job_id=job_id,
        )
        assert list(pos_repo.list_by_aisle(aisle_id, job_id=job_id)) == []
