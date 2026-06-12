"""WKR Phase 1 — optional SQL Server integration for persist partial-failure characterization.

Skipped when SQL Server test infrastructure is unavailable or the configured database
is not explicitly marked as a test database (see ``sqlserver_pytest_policy``).
"""

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
from src.infrastructure.repositories.memory_raw_label_repository import (
    MemoryRawLabelRepository,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_product_record_repository import (
    SqlProductRecordRepository,
)
from tests.support.worker_phase1.doubles import FailOnNthSavePositionRepository
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


def test_wkr_p1_t001_sql_partial_persist_characterization(sql_client_or_skip) -> None:
    """When SQL is available, per-save commits leave partial rows (confirms memory characterization)."""
    client = sql_client_or_skip
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:12]
    inv_id = f"inv-wkr-{suffix}"
    aisle_id = f"aisle-wkr-{suffix}"
    job_id = f"job-wkr-{suffix}"

    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    inner_pos = SqlPositionRepository(client)
    pos_repo = FailOnNthSavePositionRepository(inner_pos, fail_on_call=2)
    prod_repo = SqlProductRecordRepository(client)
    ev_repo = SqlEvidenceRepository(client)
    raw_repo = MemoryRawLabelRepository()

    try:
        inv_repo.save(Inventory(inv_id, "WKR SQL", InventoryStatus.PROCESSING, now, now))
        aisle_repo.save(
            Aisle(aisle_id, inv_id, "WKR", AisleStatus.PROCESSING, now, now)
        )

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
                position_repo=inner_pos,
            ),
        )

        with pytest.raises(RuntimeError, match="simulated position save failure"):
            persist.execute(
                PersistAisleResultCommand(
                    aisle_id=aisle_id,
                    job_id=job_id,
                    report=make_two_entity_hybrid_report(),
                    run_dir=Path("/tmp/wkr-sql"),
                    run_id="run",
                )
            )

        committed = list(inner_pos.list_by_aisle(aisle_id, job_id=job_id))
        assert len(committed) == 1
        first_pos = committed[0]
        assert first_pos.job_id == job_id

        products_first = list(prod_repo.list_by_position(first_pos.id))
        assert len(products_first) == 1

        evidence_first = list(ev_repo.list_by_entity("position", first_pos.id))
        assert len(evidence_first) >= 1

        all_positions = list(inner_pos.list_by_aisle(aisle_id, job_id=job_id))
        assert len(all_positions) == 1
        assert all_positions[0].id == first_pos.id

        report = make_two_entity_hybrid_report()
        second_entity_uid = report["entities"][1]["entity_uid"]
        assert not any(
            p.detected_summary_json
            and p.detected_summary_json.get("entity_uid") == second_entity_uid
            for p in all_positions
        )
    finally:
        cleanup_worker_phase1_sql_scope(
            client,
            inventory_id=inv_id,
            aisle_id=aisle_id,
            job_id=job_id,
        )
        assert list(inner_pos.list_by_aisle(aisle_id, job_id=job_id)) == []
