"""GetAisleMergeResultsUseCase — Phase 2 resolved slice."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.aisles.get_aisle_merge_results import (
    GetAisleMergeResultsCommand,
    GetAisleMergeResultsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.labels.entities import FinalCountRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository


def test_merge_results_operational_scope() -> None:
    now = datetime.now(timezone.utc)
    inv = MemoryInventoryRepository()
    aisles = MemoryAisleRepository()
    final = MemoryFinalCountRepository()
    jobs = MemoryJobRepository()
    jobs.save(
        Job(
            id="j1",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )

    inv.save(Inventory("inv-1", "X", InventoryStatus.DRAFT, now, now))
    aisles.save(
        Aisle(
            "a1",
            "inv-1",
            "A",
            AisleStatus.PROCESSED,
            now,
            now,
            operational_job_id="j1",
        )
    )
    final.save_many(
        [
            FinalCountRecord(
                id="f1",
                inventory_id="inv-1",
                aisle_id="a1",
                position_id="p1",
                sku="S",
                product_name=None,
                quantity=1,
                normalized_label_ids=[],
                review_required=False,
                explanation_summary=None,
                metadata={},
                created_at=now,
                job_id="j1",
            ),
            FinalCountRecord(
                id="f2",
                inventory_id="inv-1",
                aisle_id="a1",
                position_id="p2",
                sku="T",
                product_name=None,
                quantity=2,
                normalized_label_ids=[],
                review_required=False,
                explanation_summary=None,
                metadata={},
                created_at=now,
                job_id="j2",
            ),
        ]
    )

    uc = GetAisleMergeResultsUseCase(
        inv,
        aisles,
        final,
        ResultContextResolver(jobs),
    )
    out = uc.execute(GetAisleMergeResultsCommand(inventory_id="inv-1", aisle_id="a1"))
    assert out.result_context_source == "operational"
    assert out.resolved_job_id == "j1"
    assert len(out.records) == 1
    assert out.records[0].id == "f1"
