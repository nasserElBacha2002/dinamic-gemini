"""Phase 6 — compare use case validation and metrics."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    AisleNotFoundError,
    BenchmarkCompareJobsMustDifferError,
    BenchmarkRequiresTestInventoryError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.use_cases.compare_aisle_runs import (
    CompareAisleRunsCommand,
    CompareAisleRunsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base_deps():
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    pos_repo = MemoryPositionRepository()
    return inv_repo, aisle_repo, job_repo, pos_repo


def test_compare_requires_same_inventory_aisle_and_jobs_exist() -> None:
    inv_repo, aisle_repo, job_repo, pos_repo = _base_deps()
    now = _now()
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
            id="j1",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
            provider_name="gemini",
        )
    )
    job_repo.save(
        Job(
            id="j2",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )

    uc = CompareAisleRunsUseCase(
        inv_repo, aisle_repo, job_repo, pos_repo, positions_aisle_raw_cap=500
    )
    with pytest.raises(InventoryNotFoundError):
        uc.execute(
            CompareAisleRunsCommand(
                inventory_id="missing",
                aisle_id="a1",
                job_a_id="j1",
                job_b_id="j2",
            )
        )
    with pytest.raises(AisleNotFoundError):
        uc.execute(
            CompareAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1-wrong",
                job_a_id="j1",
                job_b_id="j2",
            )
        )
    aisle_repo.save(Aisle("a1", "inv1", "A", AisleStatus.PROCESSED, now, now))
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
        uc.execute(
            CompareAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a2",
                job_a_id="j1",
                job_b_id="j2",
            )
        )
    with pytest.raises(JobNotFoundError):
        uc.execute(
            CompareAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_a_id="jx",
                job_b_id="j2",
            )
        )
    job_repo.save(
        Job(
            id="other-aisle",
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
        uc.execute(
            CompareAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_a_id="other-aisle",
                job_b_id="j2",
            )
        )


def test_compare_rejects_identical_jobs() -> None:
    inv_repo, aisle_repo, job_repo, pos_repo = _base_deps()
    now = _now()
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
    uc = CompareAisleRunsUseCase(
        inv_repo, aisle_repo, job_repo, pos_repo, positions_aisle_raw_cap=500
    )
    with pytest.raises(BenchmarkCompareJobsMustDifferError, match="different benchmark runs"):
        uc.execute(
            CompareAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_a_id="j1",
                job_b_id="j1",
            )
        )


def test_compare_metrics_and_diff_quantity_change() -> None:
    inv_repo, aisle_repo, job_repo, pos_repo = _base_deps()
    now = _now()
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
        Aisle("a1", "inv1", "A", AisleStatus.PROCESSED, now, now, operational_job_id="j1")
    )
    for jid in ("j1", "j2"):
        job_repo.save(
            Job(
                id=jid,
                target_type="aisle",
                target_id="a1",
                job_type="process_aisle",
                status=JobStatus.SUCCEEDED,
                payload_json={},
                created_at=now,
                updated_at=now,
                provider_name="openai",
                model_name="gpt-4o-mini",
                prompt_key="global_v21",
                prompt_version="global_v21@v2.1",
                result_json={
                    "llm_cost_snapshot": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "billing_currency": "USD",
                        "usage": {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
                        "pricing_snapshot": {
                            "pricing_source": "settings.llm_pricing_catalog_json",
                            "pricing_version": "catalog-v1",
                            "billing_currency": "USD",
                        },
                        "computed_cost": {"total_cost": "0.00110000", "currency": "USD"},
                        "capture_status": "exact",
                        "capture_notes": [],
                    }
                },
            )
        )

    pos_repo.save(
        Position(
            id="p1a",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={"internal_code": "SKU1", "final_quantity": 3},
            job_id="j1",
        )
    )
    pos_repo.save(
        Position(
            id="p1b",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={"internal_code": "SKU1", "final_quantity": 5},
            job_id="j2",
        )
    )

    uc = CompareAisleRunsUseCase(
        inv_repo, aisle_repo, job_repo, pos_repo, positions_aisle_raw_cap=500
    )
    out = uc.execute(
        CompareAisleRunsCommand(
            inventory_id="inv1",
            aisle_id="a1",
            job_a_id="j1",
            job_b_id="j2",
        )
    )
    assert out["workflow"] == "benchmark_compare"
    assert out["run_a"]["metrics"]["consolidated_positions"] == 1
    assert out["run_b"]["metrics"]["consolidated_positions"] == 1
    assert out["diff_summary"]["keys_in_both"] == 1
    assert out["diff_summary"]["quantity_changed"] == 1
    assert out["diff_summary"]["keys_only_in_a"] == 0
    assert out["run_a"]["llm_cost_snapshot"] is not None
    assert out["run_a"]["llm_cost_snapshot"]["computed_cost"]["total_cost"] == "0.00110000"


def test_compare_rejects_production_inventory() -> None:
    inv_repo, aisle_repo, job_repo, pos_repo = _base_deps()
    now = _now()
    inv_repo.save(Inventory("inv-prod", "I", InventoryStatus.IN_REVIEW, now, now))
    aisle_repo.save(Aisle("a1", "inv-prod", "A", AisleStatus.PROCESSED, now, now))
    job_repo.save(
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
    job_repo.save(
        Job(
            id="j2",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    uc = CompareAisleRunsUseCase(
        inv_repo, aisle_repo, job_repo, pos_repo, positions_aisle_raw_cap=500
    )
    with pytest.raises(BenchmarkRequiresTestInventoryError):
        uc.execute(
            CompareAisleRunsCommand(
                inventory_id="inv-prod",
                aisle_id="a1",
                job_a_id="j1",
                job_b_id="j2",
            )
        )
