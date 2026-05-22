"""Phase 2: list aisle positions respects Result Context Resolver."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)


def test_list_positions_operational_job_excludes_other_runs() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    job_repo = MemoryJobRepository()
    job_repo.save(
        Job(
            id="job-op",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )

    inv_repo.save(Inventory("inv-1", "X", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(
        Aisle(
            "aisle-1",
            "inv-1",
            "A",
            AisleStatus.PROCESSED,
            now,
            now,
            operational_job_id="job-op",
        )
    )
    pos_repo.save(
        Position(
            "p-legacy",
            "aisle-1",
            PositionStatus.DETECTED,
            0.9,
            False,
            None,
            now,
            now,
            detected_summary_json={"internal_code": "L", "final_quantity": 1},
            job_id=None,
        )
    )
    pos_repo.save(
        Position(
            "p-op",
            "aisle-1",
            PositionStatus.DETECTED,
            0.9,
            False,
            None,
            now,
            now,
            detected_summary_json={"internal_code": "O", "final_quantity": 1},
            job_id="job-op",
        )
    )
    pos_repo.save(
        Position(
            "p-bench",
            "aisle-1",
            PositionStatus.DETECTED,
            0.9,
            False,
            None,
            now,
            now,
            detected_summary_json={"internal_code": "B", "final_quantity": 1},
            job_id="job-bench",
        )
    )

    uc = ListAislePositionsUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        ResultContextResolver(job_repo, pos_repo),
        MemoryProductRecordRepository(),
        positions_aisle_raw_cap=500,
    )
    result = uc.execute(
        ListAislePositionsCommand(inventory_id="inv-1", aisle_id="aisle-1", page=1, page_size=50)
    )
    assert result.result_context_source == "operational"
    assert result.resolved_job_id == "job-op"
    ids = {p.id for p in result.positions}
    assert ids == {"p-op"}


def test_list_positions_legacy_null_job_only() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    job_repo = MemoryJobRepository()

    inv_repo.save(Inventory("inv-1", "X", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A", AisleStatus.PROCESSED, now, now))
    pos_repo.save(
        Position(
            "p-legacy",
            "aisle-1",
            PositionStatus.DETECTED,
            0.9,
            False,
            None,
            now,
            now,
            detected_summary_json={"internal_code": "L", "final_quantity": 1},
            job_id=None,
        )
    )
    pos_repo.save(
        Position(
            "p-other",
            "aisle-1",
            PositionStatus.DETECTED,
            0.9,
            False,
            None,
            now,
            now,
            detected_summary_json={"internal_code": "O", "final_quantity": 1},
            job_id="job-x",
        )
    )

    uc = ListAislePositionsUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        ResultContextResolver(job_repo, pos_repo),
        MemoryProductRecordRepository(),
        positions_aisle_raw_cap=500,
    )
    result = uc.execute(
        ListAislePositionsCommand(inventory_id="inv-1", aisle_id="aisle-1", page=1, page_size=50)
    )
    assert result.result_context_source == "legacy"
    assert result.resolved_job_id is None
    assert {p.id for p in result.positions} == {"p-legacy"}


def test_list_positions_explicit_job_id_returns_job_scoped_when_operational_unset() -> None:
    """Default read can be empty for job-only data; explicit job_id resolves the slice (Phase 2)."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    job_repo = MemoryJobRepository()
    job_repo.save(
        Job(
            id="job-only",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )

    inv_repo.save(Inventory("inv-1", "X", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(
        Aisle("aisle-1", "inv-1", "A", AisleStatus.PROCESSED, now, now, operational_job_id=None)
    )
    pos_repo.save(
        Position(
            "p-scoped",
            "aisle-1",
            PositionStatus.DETECTED,
            0.9,
            False,
            None,
            now,
            now,
            detected_summary_json={"internal_code": "S", "final_quantity": 1},
            job_id="job-only",
        )
    )

    uc = ListAislePositionsUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        ResultContextResolver(job_repo, pos_repo),
        MemoryProductRecordRepository(),
        positions_aisle_raw_cap=500,
    )
    default_result = uc.execute(
        ListAislePositionsCommand(inventory_id="inv-1", aisle_id="aisle-1", page=1, page_size=50)
    )
    assert default_result.result_context_source == "legacy"
    assert default_result.resolved_job_id is None
    assert default_result.positions == ()

    explicit = uc.execute(
        ListAislePositionsCommand(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            page=1,
            page_size=50,
            job_id="job-only",
        )
    )
    assert explicit.result_context_source == "explicit"
    assert explicit.resolved_job_id == "job-only"
    assert {p.id for p in explicit.positions} == {"p-scoped"}
