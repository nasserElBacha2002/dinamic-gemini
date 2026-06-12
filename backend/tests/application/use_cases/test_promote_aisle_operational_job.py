"""Phase 6 — promote operational job pointer."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    JobPromotionNotAllowedError,
)
from src.application.use_cases.aisles.promote_aisle_operational_job import (
    PromoteAisleOperationalJobCommand,
    PromoteAisleOperationalJobUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_operational_promotion_service_from_repos(inv_repo, aisle_repo, job_repo):
    from src.application.services.operational_result_promotion_service import (
        OperationalResultPromotionService,
    )
    from src.infrastructure.persistence.memory_operational_job_promotion_repository import (
        MemoryOperationalJobPromotionRepository,
    )

    return OperationalResultPromotionService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        promotion_repo=MemoryOperationalJobPromotionRepository(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
        ),
    )


def test_promote_only_succeeded_process_aisle_for_scoped_job() -> None:
    now = _now()
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    inv_repo.save(
        Inventory(
            "inv1",
            "I",
            InventoryStatus.IN_REVIEW,
            now,
            now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle("a1", "inv1", "A", AisleStatus.PROCESSED, now, now, operational_job_id=None)
    )
    job_repo.save(
        Job(
            id="jok",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    job_repo.save(
        Job(
            id="jfail",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.FAILED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )

    promotion = build_operational_promotion_service_from_repos(inv_repo, aisle_repo, job_repo)
    uc = PromoteAisleOperationalJobUseCase(inv_repo, aisle_repo, job_repo, promotion)
    with pytest.raises(JobPromotionNotAllowedError):
        uc.execute(PromoteAisleOperationalJobCommand("inv1", "a1", "jfail"))

    assert uc.execute(PromoteAisleOperationalJobCommand("inv1", "a1", "jok")) == "jok"
    assert aisle_repo.get_by_id("a1").operational_job_id == "jok"


def test_promote_validates_inventory_and_aisle_scope() -> None:
    now = _now()
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    inv_repo.save(
        Inventory(
            "inv1",
            "I",
            InventoryStatus.IN_REVIEW,
            now,
            now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(Aisle("a1", "inv1", "A", AisleStatus.PROCESSED, now, now))
    job_repo.save(
        Job(
            id="jok",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    promotion = build_operational_promotion_service_from_repos(inv_repo, aisle_repo, job_repo)
    uc = PromoteAisleOperationalJobUseCase(inv_repo, aisle_repo, job_repo, promotion)
    with pytest.raises(InventoryNotFoundError):
        uc.execute(PromoteAisleOperationalJobCommand("missing", "a1", "jok"))
    with pytest.raises(AisleNotFoundError):
        uc.execute(PromoteAisleOperationalJobCommand("inv1", "missing", "jok"))
    inv_repo.save(
        Inventory(
            "inv2",
            "I2",
            InventoryStatus.IN_REVIEW,
            now,
            now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(Aisle("a2", "inv2", "B", AisleStatus.PROCESSED, now, now))
    with pytest.raises(AisleNotFoundError):
        uc.execute(PromoteAisleOperationalJobCommand("inv1", "a2", "jok"))
    with pytest.raises(JobNotFoundError):
        uc.execute(PromoteAisleOperationalJobCommand("inv1", "a1", "nope"))
    job_repo.save(
        Job(
            id="j-other",
            target_type="aisle",
            target_id="other",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    with pytest.raises(JobDoesNotBelongToAisleError):
        uc.execute(PromoteAisleOperationalJobCommand("inv1", "a1", "j-other"))
