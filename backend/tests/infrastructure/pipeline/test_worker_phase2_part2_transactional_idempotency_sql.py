"""Phase 2 Part 2 — SQL Server transactional idempotency (P2-P2-T010–T012)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.services.job_result_scope_cleaner import JobResultScopeCleaner
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.persistence.sql_job_result_unit_of_work import SqlJobResultUnitOfWorkFactory
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
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
from tests.support.worker_phase1.executor_harness import (
    FixedClock,
    build_recompute_use_case,
    make_entity_hybrid_report,
    make_two_entity_hybrid_report,
)
from tests.support.worker_phase1.sql_cleanup import (
    assert_sql_integration_database_is_safe,
    cleanup_worker_phase1_sql_scope,
)
from tests.support.worker_phase2.duplicate_detection import (
    duplicate_positions_by_job_entity_uid,
    entity_uid_from_position,
)
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


def _abc_report(*, qty_a=2, include_b=True, include_c=False, qty_c=5):
    entities = [
        {
            "entity_uid": "e1",
            "entity_type": "PALLET",
            "internal_code": "SKU-A",
            "final_quantity": qty_a,
            "product_label_quantity": qty_a,
            "confidence": 0.9,
            "count_status": "COUNTED",
            "evidence_path": "evidence/crop_a.jpg",
            "source_image_id": "asset-1",
        },
    ]
    if include_b:
        entities.append(
            {
                "entity_uid": "e2",
                "entity_type": "PALLET",
                "internal_code": "SKU-B",
                "final_quantity": 4,
                "product_label_quantity": 4,
                "confidence": 0.85,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop_b.jpg",
                "source_image_id": "asset-2",
            }
        )
    if include_c:
        entities.append(
            {
                "entity_uid": "e3",
                "entity_type": "PALLET",
                "internal_code": "SKU-C",
                "final_quantity": qty_c,
                "product_label_quantity": qty_c,
                "confidence": 0.8,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop_c.jpg",
                "source_image_id": "asset-1",
            }
        )
    return make_entity_hybrid_report(entities)


def _build_sql_persist(client, *, inv_id, aisle_id, now):
    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    pos_repo = SqlPositionRepository(client)
    prod_repo = SqlProductRecordRepository(client)
    ev_repo = SqlEvidenceRepository(client)
    raw_repo = SqlRawLabelRepository(client)
    norm_repo = SqlNormalizedLabelRepository(client)
    final_repo = SqlFinalCountRepository(client)
    recompute = build_recompute_use_case(
        raw_repo=raw_repo,
        norm_repo=norm_repo,
        final_repo=final_repo,
        product_repo=prod_repo,
        position_repo=pos_repo,
    )
    persist = PersistAisleResultUseCase(
        position_repo=pos_repo,
        product_record_repo=prod_repo,
        evidence_repo=ev_repo,
        clock=FixedClock(now),
        hybrid_mapper=default_map_hybrid_report_to_domain,
        aisle_repo=aisle_repo,
        raw_label_repo=raw_repo,
        recompute_consolidated_uc=recompute,
        job_result_uow_factory=SqlJobResultUnitOfWorkFactory(client),
    )
    return persist, inv_repo, aisle_repo, pos_repo, prod_repo, ev_repo, raw_repo, norm_repo, final_repo


def test_p2_p2_t010_sql_rollback_after_deletion_preserves_snapshot(sql_client_or_skip) -> None:
    client = sql_client_or_skip
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:12]
    inv_id = f"inv-p2p2-{suffix}"
    aisle_id = f"aisle-p2p2-{suffix}"
    job_id = f"job-p2p2-{suffix}"

    persist, inv_repo, aisle_repo, pos_repo, *_ = _build_sql_persist(
        client, inv_id=inv_id, aisle_id=aisle_id, now=now
    )
    try:
        inv_repo.save(Inventory(inv_id, "P2P2", InventoryStatus.PROCESSING, now, now))
        aisle_repo.save(Aisle(aisle_id, inv_id, "P2", AisleStatus.PROCESSING, now, now))

        cmd = PersistAisleResultCommand(
            aisle_id=aisle_id,
            job_id=job_id,
            report=make_two_entity_hybrid_report(),
            run_dir=Path("/tmp/p2p2-sql"),
            run_id="run",
        )
        persist.execute(cmd)
        after_first = list(pos_repo.list_by_aisle(aisle_id, job_id=job_id))
        assert len(after_first) == 2

        def _fail() -> None:
            raise RuntimeError("sql fail after delete")

        rollback_persist = PersistAisleResultUseCase(
            position_repo=pos_repo,
            product_record_repo=SqlProductRecordRepository(client),
            evidence_repo=SqlEvidenceRepository(client),
            clock=FixedClock(now),
            hybrid_mapper=default_map_hybrid_report_to_domain,
            aisle_repo=aisle_repo,
            raw_label_repo=SqlRawLabelRepository(client),
            recompute_consolidated_uc=build_recompute_use_case(
                raw_repo=SqlRawLabelRepository(client),
                norm_repo=SqlNormalizedLabelRepository(client),
                final_repo=SqlFinalCountRepository(client),
                product_repo=SqlProductRecordRepository(client),
                position_repo=pos_repo,
            ),
            scope_cleaner=JobResultScopeCleaner(after_delete_hook=_fail),
            job_result_uow_factory=SqlJobResultUnitOfWorkFactory(client),
        )
        with pytest.raises(RuntimeError, match="sql fail after delete"):
            rollback_persist.execute(cmd)
        after_fail = list(pos_repo.list_by_aisle(aisle_id, job_id=job_id))
        assert len(after_fail) == 2
        assert duplicate_positions_by_job_entity_uid(after_fail) == {}
    finally:
        cleanup_worker_phase1_sql_scope(
            client, inventory_id=inv_id, aisle_id=aisle_id, job_id=job_id
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


def test_p2_p2_t011_sql_identical_re_persist_is_idempotent(sql_client_or_skip) -> None:
    client = sql_client_or_skip
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:12]
    inv_id = f"inv-p2p2-{suffix}"
    aisle_id = f"aisle-p2p2-{suffix}"
    job_id = f"job-p2p2-{suffix}"

    persist, inv_repo, aisle_repo, pos_repo, *_ = _build_sql_persist(
        client, inv_id=inv_id, aisle_id=aisle_id, now=now
    )
    try:
        inv_repo.save(Inventory(inv_id, "P2P2", InventoryStatus.PROCESSING, now, now))
        aisle_repo.save(Aisle(aisle_id, inv_id, "P2", AisleStatus.PROCESSING, now, now))
        cmd = PersistAisleResultCommand(
            aisle_id=aisle_id,
            job_id=job_id,
            report=make_two_entity_hybrid_report(),
            run_dir=Path("/tmp/p2p2-sql"),
            run_id="run",
        )
        persist.execute(cmd)
        persist.execute(cmd)
        positions = list(pos_repo.list_by_aisle(aisle_id, job_id=job_id))
        assert len(positions) == 2
        assert duplicate_positions_by_job_entity_uid(positions) == {}
    finally:
        cleanup_worker_phase1_sql_scope(
            client, inventory_id=inv_id, aisle_id=aisle_id, job_id=job_id
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


def test_p2_p2_t012_sql_changed_report_replaces_snapshot(sql_client_or_skip) -> None:
    client = sql_client_or_skip
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:12]
    inv_id = f"inv-p2p2-{suffix}"
    aisle_id = f"aisle-p2p2-{suffix}"
    job_id = f"job-p2p2-{suffix}"

    persist, inv_repo, aisle_repo, pos_repo, prod_repo, *_ = _build_sql_persist(
        client, inv_id=inv_id, aisle_id=aisle_id, now=now
    )
    try:
        inv_repo.save(Inventory(inv_id, "P2P2", InventoryStatus.PROCESSING, now, now))
        aisle_repo.save(Aisle(aisle_id, inv_id, "P2", AisleStatus.PROCESSING, now, now))
        persist.execute(
            PersistAisleResultCommand(
                aisle_id=aisle_id,
                job_id=job_id,
                report=_abc_report(),
                run_dir=Path("/tmp/p2p2-sql"),
                run_id="run",
            )
        )
        persist.execute(
            PersistAisleResultCommand(
                aisle_id=aisle_id,
                job_id=job_id,
                report=_abc_report(qty_a=99, include_b=False, include_c=True),
                run_dir=Path("/tmp/p2p2-sql"),
                run_id="run",
            )
        )
        positions = list(pos_repo.list_by_aisle(aisle_id, job_id=job_id))
        assert len(positions) == 2
        uids = {entity_uid_from_position(p) for p in positions}
        assert uids == {"e1", "e3"}
        products = []
        for pos in positions:
            products.extend(prod_repo.list_by_position(pos.id))
        assert {p.sku for p in products} == {"SKU-A", "SKU-C"}
    finally:
        cleanup_worker_phase1_sql_scope(
            client, inventory_id=inv_id, aisle_id=aisle_id, job_id=job_id
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
