"""Phase 2 — cross-contract: positions / analytics share ResultContextResolver SoT.

Case: jobs list ordered with historical job A first; operational pointer is B.
System must use B (never jobs[0]).
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.dto.analytics_dto import AnalyticsFilters
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.inventories.export_inventory_results import (
    append_inventory_csv_rows_for_aisle,
)
from src.application.use_cases.positions.get_position_code_scan_evidence import (
    GetPositionCodeScanEvidenceCommand,
    GetPositionCodeScanEvidenceUseCase,
)
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_analytics_repository import MemoryAnalyticsRepository
from src.infrastructure.repositories.memory_code_scan_repository import MemoryCodeScanRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_review_action_repository import (
    MemoryReviewActionRepository,
)


def _utc() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_operational_b_preferred_over_jobs_zero_index_a() -> None:
    now = _utc()
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    pos_repo = MemoryPositionRepository()

    inv_repo.save(
        Inventory(
            id="inv-1",
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            client_id="c1",
        )
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.PROCESSED,
        created_at=now,
        updated_at=now,
        operational_job_id="job-b",
    )
    aisle_repo.save(aisle)

    job_a = Job(
        id="job-a",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    job_b = Job(
        id="job-b",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job_a)
    job_repo.save(job_b)

    pos_repo.save(
        Position(
            id="pos-a",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={"internal_code": "A", "final_quantity": 1},
            job_id="job-a",
        )
    )
    pos_repo.save(
        Position(
            id="pos-b",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={"internal_code": "B", "final_quantity": 1},
            job_id="job-b",
        )
    )

    resolver = ResultContextResolver(job_repo, pos_repo)
    ctx = resolver.resolve(aisle=aisle, explicit_job_id=None)
    assert ctx.source == "operational"
    assert ctx.job_id_for_slice == "job-b"

    list_uc = ListAislePositionsUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        resolver,
        MemoryProductRecordRepository(),
        positions_aisle_raw_cap=500,
    )
    listed = list_uc.execute(
        ListAislePositionsCommand(inventory_id="inv-1", aisle_id="aisle-1", page=1, page_size=50)
    )
    assert listed.resolved_job_id == "job-b"
    assert listed.result_context_source == "operational"
    assert {p.id for p in listed.positions} == {"pos-b"}

    analytics = MemoryAnalyticsRepository(
        inv_repo,
        aisle_repo,
        pos_repo,
        MemoryProductRecordRepository(),
        MemoryReviewActionRepository(),
        job_repo,
    )
    summary = analytics.get_summary(AnalyticsFilters(inventory_id="inv-1", aisle_id="aisle-1"))
    assert summary.total_positions_in_scope == 1

    listed_jobs = list(job_repo.list_jobs_for_target("aisle", "aisle-1", limit=50))
    assert any(j.id == "job-a" for j in listed_jobs)
    assert ctx.job_id_for_slice == "job-b"


def test_export_csv_uses_operational_b_not_jobs_zero_index_a() -> None:
    """Export rows must match the same resolver slice as positions list / memory analytics."""
    now = _utc()
    job_repo = MemoryJobRepository()
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.PROCESSED,
        created_at=now,
        updated_at=now,
        operational_job_id="job-b",
    )
    job_repo.save(
        Job(
            id="job-a",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    job_repo.save(
        Job(
            id="job-b",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    positions = [
        Position(
            id="pos-a",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            job_id="job-a",
        ),
        Position(
            id="pos-b",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            job_id="job-b",
        ),
    ]

    resolver = ResultContextResolver(job_repo)
    rows: list[dict] = []
    append_inventory_csv_rows_for_aisle(
        rows,
        inv=Inventory(
            id="inv-1", name="Inv", status=InventoryStatus.DRAFT, created_at=now, updated_at=now
        ),
        aisle=aisle,
        aisle_sequence=1,
        resolver=resolver,
        explicit_job_id=None,
        aisle_positions=positions,
        product_record_repo=MemoryProductRecordRepository(),
        technical=False,
    )

    assert len(rows) == 1
    assert rows[0]["position_id"] == "pos-b"


def test_code_scan_evidence_filters_by_position_id_regardless_of_operational_pointer() -> None:
    """Evidence bypasses the resolver (``get_latest_run_by_aisle``) but must still stay scoped
    to the requested ``position_id`` — a non-operational job's position must never see another
    position's detections, even though the run summary itself ignores ``operational_job_id``."""
    now = _utc()
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    code_scan_repo = MemoryCodeScanRepository()

    inv_repo.save(
        Inventory(
            id="inv-1", name="Inv", status=InventoryStatus.DRAFT, created_at=now, updated_at=now
        )
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.PROCESSED,
        created_at=now,
        updated_at=now,
        operational_job_id="job-b",
    )
    aisle_repo.save(aisle)
    pos_repo.save(
        Position(
            id="pos-a",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            job_id="job-a",
        )
    )
    pos_repo.save(
        Position(
            id="pos-b",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            job_id="job-b",
        )
    )

    run = CodeScanRun(
        id="run-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        status=CodeScanRunStatus.COMPLETED,
        total_assets=1,
        processed_assets=1,
        failed_assets=0,
        total_codes_found=2,
        total_qr_found=2,
        total_barcodes_found=0,
        started_at=now,
        finished_at=now,
        scanner_engine="test",
        is_latest=True,
    )
    code_scan_repo.save_run(run)
    code_scan_repo.save_detections(
        [
            CodeScanDetection(
                id="det-a",
                run_id="run-1",
                inventory_id="inv-1",
                aisle_id="aisle-1",
                asset_id="asset-a",
                code_type=CodeType.QR,
                code_value="A-CODE",
                normalized_code_value="A-CODE",
                detection_status=CodeScanDetectionStatus.DETECTED,
                scanner_engine="test",
                created_at=now,
                matched_position_id="pos-a",
            ),
            CodeScanDetection(
                id="det-b",
                run_id="run-1",
                inventory_id="inv-1",
                aisle_id="aisle-1",
                asset_id="asset-b",
                code_type=CodeType.QR,
                code_value="B-CODE",
                normalized_code_value="B-CODE",
                detection_status=CodeScanDetectionStatus.DETECTED,
                scanner_engine="test",
                created_at=now,
                matched_position_id="pos-b",
            ),
        ]
    )

    uc = GetPositionCodeScanEvidenceUseCase(inv_repo, aisle_repo, pos_repo, code_scan_repo)

    # The non-operational position (job-a) must only ever see its own detections — the shared
    # "latest run" summary is not itself a leak vector because detections stay position-scoped.
    result_a = uc.execute(
        GetPositionCodeScanEvidenceCommand(
            inventory_id="inv-1", aisle_id="aisle-1", position_id="pos-a"
        )
    )
    assert result_a.latest_run is not None and result_a.latest_run.id == "run-1"
    assert {d.id for d in result_a.detections} == {"det-a"}

    result_b = uc.execute(
        GetPositionCodeScanEvidenceCommand(
            inventory_id="inv-1", aisle_id="aisle-1", position_id="pos-b"
        )
    )
    assert result_b.latest_run is not None and result_b.latest_run.id == "run-1"
    assert {d.id for d in result_b.detections} == {"det-b"}
