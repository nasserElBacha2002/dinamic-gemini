"""Phase 2 Part 3 — SQL promotion and cleanup (P2-P3-T014–T016)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.application.ports.operational_job_promotion import PromotionOutcome
from src.application.services.operational_result_promotion_service import (
    OperationalResultPromotionService,
)
from src.application.use_cases.pipeline.cleanup_job_results import (
    CleanupJobResultsCommand,
    CleanupJobResultsOutcome,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.persistence.sql_operational_job_promotion_repository import (
    SqlOperationalJobPromotionRepository,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
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


def _promotion_service(client, inv_repo, aisle_repo, job_repo):
    return OperationalResultPromotionService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        promotion_repo=SqlOperationalJobPromotionRepository(client),
    )


def test_p2_p3_t014_sql_compare_and_set_promotion(sql_client_or_skip) -> None:
    client = sql_client_or_skip
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:12]
    inv_id = f"inv-p3-{suffix}"
    aisle_id = f"aisle-p3-{suffix}"
    job_old = f"job-p3-old-{suffix}"
    job_new = f"job-p3-new-{suffix}"

    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    job_repo = SqlJobRepository(client)
    promo = _promotion_service(client, inv_repo, aisle_repo, job_repo)

    try:
        inv_repo.save(Inventory(inv_id, "P3", InventoryStatus.PROCESSING, now, now))
        aisle_repo.save(Aisle(aisle_id, inv_id, "P3", AisleStatus.PROCESSING, now, now))
        job_repo.save(
            Job(
                job_old,
                "aisle",
                aisle_id,
                "process_aisle",
                JobStatus.SUCCEEDED,
                {},
                now,
                now,
            )
        )
        job_repo.save(
            Job(
                job_new,
                "aisle",
                aisle_id,
                "process_aisle",
                JobStatus.SUCCEEDED,
                {},
                now + timedelta(minutes=5),
                now + timedelta(minutes=5),
            )
        )
        assert promo.promote_for_success(aisle_id=aisle_id, candidate_job_id=job_new).outcome == PromotionOutcome.PROMOTED
        stale = promo.promote_for_success(aisle_id=aisle_id, candidate_job_id=job_old)
        assert stale.outcome == PromotionOutcome.REJECTED_STALE
        assert aisle_repo.get_by_id(aisle_id).operational_job_id == job_new
    finally:
        cleanup_worker_phase1_sql_scope(
            client, inventory_id=inv_id, aisle_id=aisle_id, job_id=job_old
        )
        cleanup_worker_phase1_sql_scope(
            client, inventory_id=inv_id, aisle_id=aisle_id, job_id=job_new
        )


def test_p2_p3_t016_sql_cleanup_protects_operational_job(sql_client_or_skip) -> None:
    """Operational job cleanup rejected at application layer (SQL-backed repos)."""
    from src.application.ports.job_result_unit_of_work import JobResultRepositories
    from src.application.use_cases.pipeline.cleanup_job_results import CleanupJobResultsUseCase
    from src.infrastructure.persistence.sql_job_result_unit_of_work import (
        SqlJobResultUnitOfWorkFactory,
    )
    from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository
    from src.infrastructure.repositories.sql_final_count_repository import SqlFinalCountRepository
    from src.infrastructure.repositories.sql_normalized_label_repository import (
        SqlNormalizedLabelRepository,
    )
    from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
    from src.infrastructure.repositories.sql_product_record_repository import (
        SqlProductRecordRepository,
    )
    from src.infrastructure.repositories.sql_raw_label_repository import SqlRawLabelRepository
    from src.infrastructure.repositories.sql_result_evidence_repository import (
        SqlResultEvidenceRepository,
    )

    client = sql_client_or_skip
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:12]
    inv_id = f"inv-p3c-{suffix}"
    aisle_id = f"aisle-p3c-{suffix}"
    job_id = f"job-p3c-{suffix}"

    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    job_repo = SqlJobRepository(client)
    repos = JobResultRepositories(
        position_repo=SqlPositionRepository(client),
        product_record_repo=SqlProductRecordRepository(client),
        evidence_repo=SqlEvidenceRepository(client),
        raw_label_repo=SqlRawLabelRepository(client),
        normalized_label_repo=SqlNormalizedLabelRepository(client),
        final_count_repo=SqlFinalCountRepository(client),
        result_evidence_repo=SqlResultEvidenceRepository(client),
    )
    cleanup = CleanupJobResultsUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_result_uow_factory=SqlJobResultUnitOfWorkFactory(client),
        repositories=repos,
    )

    try:
        inv_repo.save(Inventory(inv_id, "P3", InventoryStatus.PROCESSING, now, now))
        aisle = Aisle(
            aisle_id, inv_id, "P3", AisleStatus.PROCESSED, now, now, operational_job_id=job_id
        )
        aisle_repo.save(aisle)
        job_repo.save(
            Job(job_id, "aisle", aisle_id, "process_aisle", JobStatus.SUCCEEDED, {}, now, now)
        )
        result = cleanup.execute(
            CleanupJobResultsCommand(inventory_id=inv_id, aisle_id=aisle_id, job_id=job_id)
        )
        assert result.outcome == CleanupJobResultsOutcome.REJECTED_OPERATIONAL_JOB
    finally:
        cleanup_worker_phase1_sql_scope(
            client, inventory_id=inv_id, aisle_id=aisle_id, job_id=job_id
        )
