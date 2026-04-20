"""Phase 1 — compare-many use case (baseline-centric, max 3 jobs)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    BenchmarkCompareManyInvalidSelectionError,
    BenchmarkRequiresTestInventoryError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.use_cases.compare_many_aisle_runs import (
    CompareManyAisleRunsCommand,
    CompareManyAisleRunsUseCase,
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


def _build_use_case():
    return (
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryJobRepository(),
        MemoryPositionRepository(),
    )


def _seed_base(inv_mode: InventoryProcessingMode = InventoryProcessingMode.TEST):
    inv_repo, aisle_repo, job_repo, pos_repo = _build_use_case()
    now = _now()
    inv_repo.save(Inventory("inv1", "Inv", InventoryStatus.IN_REVIEW, now, now, processing_mode=inv_mode))
    aisle_repo.save(Aisle("a1", "inv1", "A", AisleStatus.PROCESSED, now, now))
    for job_id in ("j1", "j2", "j3"):
        job_repo.save(
            Job(
                id=job_id,
                target_type="aisle",
                target_id="a1",
                job_type="process_aisle",
                status=JobStatus.SUCCEEDED,
                payload_json={},
                created_at=now,
                updated_at=now,
                provider_name="openai",
            )
        )
    pos_repo.save(
        Position(
            id="p-j1",
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
            id="p-j2",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={"internal_code": "SKU1", "final_quantity": 4},
            job_id="j2",
        )
    )
    pos_repo.save(
        Position(
            id="p-j3",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=True,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={"internal_code": "SKU3", "final_quantity": 1},
            job_id="j3",
        )
    )
    return CompareManyAisleRunsUseCase(
        inv_repo,
        aisle_repo,
        job_repo,
        pos_repo,
        positions_aisle_raw_cap=500,
    ), job_repo


def test_compare_many_valid_two_jobs() -> None:
    uc, _ = _seed_base()
    out = uc.execute(
        CompareManyAisleRunsCommand(
            inventory_id="inv1",
            aisle_id="a1",
            job_ids=["j1", "j2"],
            baseline_job_id="j1",
        )
    )
    assert out["baseline_job_id"] == "j1"
    assert [j["job_id"] for j in out["jobs"]] == ["j1", "j2"]
    assert len(out["comparisons"]) == 1
    assert out["comparisons"][0]["target_job_id"] == "j2"


def test_compare_many_valid_three_jobs_preserves_order_and_baseline_targets() -> None:
    uc, _ = _seed_base()
    out = uc.execute(
        CompareManyAisleRunsCommand(
            inventory_id="inv1",
            aisle_id="a1",
            job_ids=["j3", "j1", "j2"],
            baseline_job_id="j1",
        )
    )
    assert [j["job_id"] for j in out["jobs"]] == ["j3", "j1", "j2"]
    assert [c["target_job_id"] for c in out["comparisons"]] == ["j3", "j2"]


def test_compare_many_duplicate_ids_rejected() -> None:
    uc, _ = _seed_base()
    with pytest.raises(BenchmarkCompareManyInvalidSelectionError, match="unique"):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", "j1"],
                baseline_job_id="j1",
            )
        )


def test_compare_many_too_few_jobs_rejected() -> None:
    uc, _ = _seed_base()
    with pytest.raises(BenchmarkCompareManyInvalidSelectionError, match="At least 2"):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1"],
                baseline_job_id="j1",
            )
        )


def test_compare_many_too_many_jobs_rejected() -> None:
    uc, _ = _seed_base()
    with pytest.raises(BenchmarkCompareManyInvalidSelectionError, match="At most 3"):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", "j2", "j3", "j4"],
                baseline_job_id="j1",
            )
        )


def test_compare_many_baseline_missing_from_ids_rejected() -> None:
    uc, _ = _seed_base()
    with pytest.raises(BenchmarkCompareManyInvalidSelectionError, match="must be one of job_ids"):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", "j2"],
                baseline_job_id="j3",
            )
        )


def test_compare_many_cross_aisle_job_rejected() -> None:
    uc, job_repo = _seed_base()
    now = _now()
    job_repo.save(
        Job(
            id="j-other",
            target_type="aisle",
            target_id="other-aisle",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    with pytest.raises(JobDoesNotBelongToAisleError):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", "j-other"],
                baseline_job_id="j1",
            )
        )


def test_compare_many_missing_job_rejected() -> None:
    uc, _ = _seed_base()
    with pytest.raises(JobNotFoundError):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", "missing"],
                baseline_job_id="j1",
            )
        )


def test_compare_many_rejects_production_inventory() -> None:
    uc, _ = _seed_base(inv_mode=InventoryProcessingMode.PRODUCTION)
    with pytest.raises(BenchmarkRequiresTestInventoryError):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", "j2"],
                baseline_job_id="j1",
            )
        )


def test_compare_many_rejects_baseline_whitespace_after_trim() -> None:
    uc, _ = _seed_base()
    with pytest.raises(BenchmarkCompareManyInvalidSelectionError, match="baseline_job_id is required"):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", "j2"],
                baseline_job_id="   ",
            )
        )


def test_compare_many_rejects_empty_job_ids_after_trim() -> None:
    uc, _ = _seed_base()
    with pytest.raises(BenchmarkCompareManyInvalidSelectionError, match="whitespace-only"):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", " ", "j2"],
                baseline_job_id="j1",
            )
        )


def test_compare_many_rejects_duplicate_job_ids_after_trim() -> None:
    uc, _ = _seed_base()
    with pytest.raises(BenchmarkCompareManyInvalidSelectionError, match="unique"):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", " j1 "],
                baseline_job_id="j1",
            )
        )


def test_compare_many_truncation_flag_is_truthful() -> None:
    inv_repo, aisle_repo, job_repo, pos_repo = _build_use_case()
    now = _now()
    inv_repo.save(Inventory("inv1", "Inv", InventoryStatus.IN_REVIEW, now, now, processing_mode=InventoryProcessingMode.TEST))
    aisle_repo.save(Aisle("a1", "inv1", "A", AisleStatus.PROCESSED, now, now))
    for job_id in ("j1", "j2"):
        job_repo.save(
            Job(
                id=job_id,
                target_type="aisle",
                target_id="a1",
                job_type="process_aisle",
                status=JobStatus.SUCCEEDED,
                payload_json={},
                created_at=now,
                updated_at=now,
            )
        )
    # j1 has exactly 1 row; j2 has 2 rows. With raw cap=1 only j2 should be truly truncated.
    pos_repo.save(
        Position(
            id="p1",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={"internal_code": "S1", "final_quantity": 1},
            job_id="j1",
        )
    )
    for pid in ("p2a", "p2b"):
        pos_repo.save(
            Position(
                id=pid,
                aisle_id="a1",
                status=PositionStatus.DETECTED,
                confidence=0.9,
                needs_review=False,
                primary_evidence_id=None,
                created_at=now,
                updated_at=now,
                detected_summary_json={"internal_code": "S2", "final_quantity": 1},
                job_id="j2",
            )
        )
    uc = CompareManyAisleRunsUseCase(
        inv_repo,
        aisle_repo,
        job_repo,
        pos_repo,
        positions_aisle_raw_cap=1,
    )
    out = uc.execute(
        CompareManyAisleRunsCommand(
            inventory_id="inv1",
            aisle_id="a1",
            job_ids=["j1", "j2"],
            baseline_job_id="j1",
        )
    )
    flags = {f["job_id"]: f["truncated"] for f in out["raw_fetch_truncated"]}
    assert flags["j1"] is False
    assert flags["j2"] is True


def test_compare_many_can_include_diff_rows_with_cap() -> None:
    uc, _ = _seed_base()
    out = uc.execute(
        CompareManyAisleRunsCommand(
            inventory_id="inv1",
            aisle_id="a1",
            job_ids=["j1", "j2", "j3"],
            baseline_job_id="j1",
            include_diff_rows=True,
            max_diff_rows=1,
        )
    )
    assert len(out["comparisons"]) == 2
    for comp in out["comparisons"]:
        assert "diff_rows" in comp
        assert len(comp["diff_rows"]) <= 1
        assert "diff_rows_truncated" in comp


def test_compare_many_default_excludes_diff_rows_payload() -> None:
    uc, _ = _seed_base()
    out = uc.execute(
        CompareManyAisleRunsCommand(
            inventory_id="inv1",
            aisle_id="a1",
            job_ids=["j1", "j2"],
            baseline_job_id="j1",
        )
    )
    comp = out["comparisons"][0]
    assert "diff_rows" not in comp
    assert "diff_rows_truncated" not in comp


def test_compare_many_rejects_max_diff_rows_above_cap() -> None:
    uc, _ = _seed_base()
    with pytest.raises(BenchmarkCompareManyInvalidSelectionError, match="<= 250"):
        uc.execute(
            CompareManyAisleRunsCommand(
                inventory_id="inv1",
                aisle_id="a1",
                job_ids=["j1", "j2"],
                baseline_job_id="j1",
                include_diff_rows=True,
                max_diff_rows=251,
            )
        )


def test_compare_many_allows_non_succeeded_jobs_for_ab_parity() -> None:
    uc, job_repo = _seed_base()
    job = job_repo.get_by_id("j2")
    assert job is not None
    job.status = JobStatus.QUEUED
    job_repo.save(job)
    out = uc.execute(
        CompareManyAisleRunsCommand(
            inventory_id="inv1",
            aisle_id="a1",
            job_ids=["j1", "j2"],
            baseline_job_id="j1",
        )
    )
    assert [j["job_id"] for j in out["jobs"]] == ["j1", "j2"]
