"""Phase 2 Part 2 corrections — structural and contract tests (P2-P2-C001–C013)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.ports.job_result_unit_of_work import JobResultRepositories
from src.application.services.default_job_scoped_recompute_factory import (
    DefaultJobScopedRecomputeFactory,
)
from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultUseCase
from src.database.sqlserver import SqlServerClient
from src.domain.evidence.entities import Evidence
from src.infrastructure.database.sql_transaction import (
    SqlServerTransaction,
    TransactionState,
    sql_repository_cursor,
)
from src.infrastructure.persistence.job_result_bundle_validation import assert_sql_job_result_bundle
from src.infrastructure.persistence.memory_job_result_unit_of_work import (
    MemoryJobResultUnitOfWorkFactory,
)
from src.infrastructure.persistence.sql_job_result_unit_of_work import SqlJobResultUnitOfWorkFactory
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from tests.support.worker_phase1.executor_harness import (
    ExecutorHarness,
    FixedClock,
    make_two_entity_hybrid_report,
)
from tests.support.worker_phase2.recompute_doubles import SpyJobScopedRecomputeFactory
from tests.support.worker_phase2.uow_doubles import SpyScopeStoreUnitOfWorkFactory


def _memory_repos(harness: ExecutorHarness) -> JobResultRepositories:
    return JobResultRepositories(
        position_repo=harness.position_repo,
        product_record_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
        result_evidence_repo=MemoryResultEvidenceRepository(),
    )


def test_p2_p2_c001_explicit_uow_required(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    with pytest.raises(ValueError, match="explicit JobResultUnitOfWorkFactory"):
        PersistAisleResultUseCase(
            position_repo=harness.position_repo,
            product_record_repo=harness.product_repo,
            evidence_repo=harness.evidence_repo,
            clock=FixedClock(harness.now),
            hybrid_mapper=__import__(
                "src.infrastructure.pipeline.hybrid_report_to_domain_adapter",
                fromlist=["default_map_hybrid_report_to_domain"],
            ).default_map_hybrid_report_to_domain,
            aisle_repo=harness.aisle_repo,
            raw_label_repo=harness.raw_repo,
            normalized_label_repo=harness.norm_repo,
            final_count_repo=harness.final_repo,
            result_evidence_repo=MemoryResultEvidenceRepository(),
            job_scoped_recompute_factory=DefaultJobScopedRecomputeFactory(),
            job_result_uow_factory=None,  # type: ignore[arg-type]
        )


def test_p2_p2_c002_memory_uow_explicit_injection(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    harness.persist_report(make_two_entity_hybrid_report())
    assert len(harness.positions_for_job()) == 2


def test_p2_p2_c003_sql_memory_factory_mismatch_rejected(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    repos = _memory_repos(harness)
    client = SqlServerClient("DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=test;")
    with pytest.raises(ValueError, match="SqlJobResultUnitOfWorkFactory requires SQL"):
        SqlJobResultUnitOfWorkFactory(client)(repos)
    from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository

    sql_repos = JobResultRepositories(
        position_repo=SqlPositionRepository(client),
        product_record_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
        result_evidence_repo=MemoryResultEvidenceRepository(),
    )
    with pytest.raises(ValueError, match="MemoryJobResultUnitOfWorkFactory requires memory"):
        MemoryJobResultUnitOfWorkFactory()(sql_repos)


def test_p2_p2_c004_scope_store_contract_used(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    spy_factory = SpyScopeStoreUnitOfWorkFactory()
    persist = harness.make_persist_use_case(job_result_uow_factory=spy_factory)
    from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultCommand

    persist.execute(
        PersistAisleResultCommand(
            aisle_id=harness.aisle_id,
            job_id=harness.job_id,
            report=make_two_entity_hybrid_report(),
            run_dir=tmp_path,
        )
    )
    assert spy_factory.spy is not None
    assert spy_factory.spy.delete_calls == 1


def test_p2_p2_c005_cursor_closes_on_success() -> None:
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value = cursor

    with sql_repository_cursor(None, connection=connection) as cur:
        assert cur is cursor
    cursor.close.assert_called_once()


def test_p2_p2_c006_cursor_closes_on_exception() -> None:
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value = cursor

    with pytest.raises(RuntimeError, match="boom"):
        with sql_repository_cursor(None, connection=connection):
            raise RuntimeError("boom")
    cursor.close.assert_called_once()


def test_p2_p2_c007_polymorphic_evidence_preserved_memory(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-ev")
    pos_repo = MemoryPositionRepository()
    ev_repo = MemoryEvidenceRepository()
    harness = ExecutorHarness.build(
        tmp_path, job_id="job-ev", position_repo=pos_repo, evidence_repo=ev_repo
    )
    from src.domain.evidence.entities import EvidenceType
    from src.domain.positions.entities import Position, PositionStatus

    shared_id = "shared-entity-id"
    pos = Position(
        id=shared_id,
        aisle_id=harness.aisle_id,
        job_id="job-ev",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=harness.now,
        updated_at=harness.now,
    )
    pos_repo.save(pos)
    ev_repo.save(
        Evidence(
            id="ev-position",
            entity_type="position",
            entity_id=shared_id,
            type=EvidenceType.POSITION_CROP,
            storage_path="p.jpg",
            is_primary=True,
        )
    )
    ev_repo.save(
        Evidence(
            id="ev-other",
            entity_type="another_type",
            entity_id=shared_id,
            type=EvidenceType.POSITION_CROP,
            storage_path="o.jpg",
            is_primary=True,
        )
    )
    from src.infrastructure.persistence.memory_job_result_scope_store import (
        MemoryJobResultScopeStore,
    )

    MemoryJobResultScopeStore(_memory_repos(harness)).delete_scope(
        inventory_id=harness.inventory_id,
        aisle_id=harness.aisle_id,
        job_id="job-ev",
    )
    assert ev_repo.get_by_id("ev-position") is None
    assert ev_repo.get_by_id("ev-other") is not None


def test_p2_p2_c008_public_recompute_contract(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    inner = DefaultJobScopedRecomputeFactory()
    spy_factory = SpyJobScopedRecomputeFactory(inner)
    persist = harness.make_persist_use_case(job_scoped_recompute_factory=spy_factory)
    from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultCommand

    persist.execute(
        PersistAisleResultCommand(
            aisle_id=harness.aisle_id,
            job_id=harness.job_id,
            report=make_two_entity_hybrid_report(),
            run_dir=tmp_path,
        )
    )
    assert spy_factory.create_calls == 1
    assert spy_factory.last_repositories is not None


def test_p2_p2_c009_single_rollback_ownership() -> None:
    connection_string = "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=test;"
    tx = SqlServerTransaction(connection_string)
    mock_conn = MagicMock()
    tx._conn = mock_conn
    tx._state = TransactionState.ACTIVE

    tx.rollback()
    assert mock_conn.rollback.call_count == 1
    tx.rollback()
    assert mock_conn.rollback.call_count == 1
    tx.close()
    mock_conn.close.assert_called_once()


def test_p2_p2_c010_commit_lifecycle() -> None:
    tx = SqlServerTransaction(
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=test;"
    )
    mock_conn = MagicMock()
    tx._conn = mock_conn
    tx._state = TransactionState.ACTIVE
    tx.commit()
    assert mock_conn.commit.call_count == 1
    assert tx.state == TransactionState.COMMITTED
    tx.close()
    mock_conn.close.assert_called_once()


def test_p2_p2_c011_exception_after_commit_does_not_rerollback() -> None:
    tx = SqlServerTransaction(
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=test;"
    )
    mock_conn = MagicMock()
    tx._conn = mock_conn
    tx._state = TransactionState.ACTIVE
    tx.commit()
    tx.rollback()
    assert mock_conn.rollback.call_count == 0


def test_p2_p2_c012_sql_shared_connection() -> None:
    from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository
    from src.infrastructure.repositories.sql_final_count_repository import SqlFinalCountRepository
    from src.infrastructure.repositories.sql_normalized_label_repository import (
        SqlNormalizedLabelRepository,
    )
    from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
    from src.infrastructure.repositories.sql_product_record_repository import (
        SqlProductRecordRepository,
    )
    from src.infrastructure.repositories.sql_result_evidence_repository import (
        SqlResultEvidenceRepository,
    )

    client = SqlServerClient("DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=test;")
    harness = ExecutorHarness.build(Path("/tmp/x"), job_id="j")
    memory_bundle = _memory_repos(harness)
    with pytest.raises(ValueError, match="SqlJobResultUnitOfWorkFactory requires SQL"):
        SqlJobResultUnitOfWorkFactory(client)(memory_bundle)

    sql_bundle = JobResultRepositories(
        position_repo=SqlPositionRepository(client),
        product_record_repo=SqlProductRecordRepository(client),
        evidence_repo=SqlEvidenceRepository(client),
        raw_label_repo=SqlRawLabelRepository(client),
        normalized_label_repo=SqlNormalizedLabelRepository(client),
        final_count_repo=SqlFinalCountRepository(client),
        result_evidence_repo=SqlResultEvidenceRepository(client),
    )
    assert_sql_job_result_bundle(sql_bundle)

    mock_conn = MagicMock()
    tx = MagicMock()
    tx.connection = mock_conn
    client.begin_transaction = MagicMock(return_value=tx)  # type: ignore[method-assign]

    uow = SqlJobResultUnitOfWorkFactory(client)(sql_bundle)
    with uow:
        assert uow.scope_store is not None
        assert uow.finalization_evidence is not None
        conn = mock_conn
        repos = uow.repositories
        for repo in (
            repos.position_repo,
            repos.product_record_repo,
            repos.evidence_repo,
            repos.raw_label_repo,
            repos.normalized_label_repo,
            repos.final_count_repo,
        ):
            assert getattr(repo, "_connection", None) is conn
