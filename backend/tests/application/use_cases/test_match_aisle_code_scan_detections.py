"""Tests for MatchAisleCodeScanDetectionsUseCase (Phase 4 read-only matching)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import (
    JOB_ID_FILTER_UNSET,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.use_cases.match_aisle_code_scan_detections import (
    MISSING_RESULT_CONTEXT_WARNING,
    MatchAisleCodeScanDetectionsCommand,
    MatchAisleCodeScanDetectionsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.domain.code_scans.matching import CodeScanMatchStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_code_scan_repository import MemoryCodeScanRepository
from tests.application.use_cases.test_run_aisle_code_scan import FixedClock, StubAisleRepo


class StubPositionRepo(PositionRepository):
    def __init__(self, positions: Sequence[Position]) -> None:
        self._positions = list(positions)
        self.last_job_filter: object = JOB_ID_FILTER_UNSET

    def save(self, position: Position) -> None:
        self._positions = [p for p in self._positions if p.id != position.id] + [position]

    def get_by_id(self, position_id: str) -> Position | None:
        return next((p for p in self._positions if p.id == position_id), None)

    def list_by_aisle(
        self,
        aisle_id: str,
        status: str | None = None,
        needs_review: bool | None = None,
        min_confidence: float | None = None,
        sku_filter: str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
        job_id=JOB_ID_FILTER_UNSET,
    ) -> Sequence[Position]:
        self.last_job_filter = job_id
        rows = [p for p in self._positions if p.aisle_id == aisle_id]
        if job_id is not JOB_ID_FILTER_UNSET:
            if job_id is None:
                rows = [p for p in rows if p.job_id is None]
            else:
                rows = [p for p in rows if p.job_id == job_id]
        if status is not None:
            rows = [p for p in rows if p.status.value == status]
        return rows

    def list_by_aisle_query(self, aisle_id: str, query=None) -> Sequence[Position]:
        return self.list_by_aisle(aisle_id)

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        return [p for p in self._positions if p.aisle_id in aisle_ids]


class StubProductRepo(ProductRecordRepository):
    def __init__(self, products: Sequence[ProductRecord]) -> None:
        self._products = list(products)
        self.saved: list[ProductRecord] = []

    def save(self, product: ProductRecord) -> None:
        self.saved.append(product)
        self._products = [p for p in self._products if p.id != product.id] + [product]

    def get_by_id(self, product_id: str) -> ProductRecord | None:
        return next((p for p in self._products if p.id == product_id), None)

    def list_by_position(self, position_id: str) -> Sequence[ProductRecord]:
        return [p for p in self._products if p.position_id == position_id]

    def list_by_position_ids(self, position_ids: Sequence[str]) -> Sequence[ProductRecord]:
        ids = set(position_ids)
        return [p for p in self._products if p.position_id in ids]


class StubJobRepo(JobRepository):
    def __init__(self, jobs: Sequence[Job] | None = None) -> None:
        self._jobs = {j.id: j for j in (jobs or [])}

    def save(self, job: Job) -> None:
        self._jobs[job.id] = job

    def get_by_id(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        matches = [
            j
            for j in self._jobs.values()
            if j.target_type == target_type and j.target_id == target_id
        ]
        return matches[0] if matches else None

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> dict[str, Job]:
        return {
            tid: job
            for tid in target_ids
            if (job := self.get_latest_by_target(target_type, tid)) is not None
        }

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        return [
            j
            for j in self._jobs.values()
            if j.target_type == target_type and j.target_id == target_id
        ]

    def list_all_jobs(self) -> Sequence[Job]:
        return list(self._jobs.values())

    def list_jobs_for_metrics(self, *args, **kwargs) -> Sequence[Job]:
        return []

    def list_jobs_for_metrics_by_finished_at(self, *args, **kwargs) -> Sequence[Job]:
        return []


def _now() -> datetime:
    return datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def _aisle(*, operational_job_id: str | None = None) -> Aisle:
    now = _now()
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.ASSETS_UPLOADED,
        created_at=now,
        updated_at=now,
        operational_job_id=operational_job_id,
    )


def _job(job_id: str) -> Job:
    now = _now()
    return Job(
        id=job_id,
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )


def _run_and_detection(
    *,
    norm: str,
    detection_id: str = "d1",
    detection_status: CodeScanDetectionStatus = CodeScanDetectionStatus.DETECTED,
) -> tuple[MemoryCodeScanRepository, str]:
    repo = MemoryCodeScanRepository()
    now = _now()
    run = CodeScanRun(
        id="run-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        status=CodeScanRunStatus.COMPLETED,
        total_assets=1,
        processed_assets=1,
        failed_assets=0,
        total_codes_found=1,
        total_qr_found=0,
        total_barcodes_found=1,
        started_at=now,
        finished_at=now,
        scanner_engine="fake",
        is_latest=True,
    )
    repo.replace_latest_run(run)
    repo.save_detections(
        [
            CodeScanDetection(
                id=detection_id,
                run_id="run-1",
                inventory_id="inv-1",
                aisle_id="aisle-1",
                asset_id="asset-1",
                code_type=CodeType.BARCODE,
                code_value=norm,
                normalized_code_value=norm,
                detection_status=detection_status,
                scanner_engine="fake",
                created_at=now,
            )
        ]
    )
    return repo, detection_id


def _position(
    position_id: str,
    *,
    job_id: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    summary: dict | None = None,
    corrected_position_code: str | None = None,
) -> Position:
    now = _now()
    return Position(
        id=position_id,
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json=summary,
        corrected_position_code=corrected_position_code,
        job_id=job_id,
    )


def _product(position_id: str, sku: str) -> ProductRecord:
    now = _now()
    return ProductRecord(
        id=f"prod-{position_id}-{sku}",
        position_id=position_id,
        sku=sku,
        detected_quantity=1,
        confidence=0.9,
        created_at=now,
        updated_at=now,
    )


def _use_case(
    *,
    repo: MemoryCodeScanRepository,
    aisle: Aisle,
    positions: Sequence[Position],
    products: Sequence[ProductRecord],
    jobs: Sequence[Job] | None = None,
) -> tuple[MatchAisleCodeScanDetectionsUseCase, StubPositionRepo]:
    position_repo = StubPositionRepo(positions)
    uc = MatchAisleCodeScanDetectionsUseCase(
        aisle_repo=StubAisleRepo(aisle),
        job_repo=StubJobRepo(jobs),
        position_repo=position_repo,
        product_record_repo=StubProductRepo(products),
        code_scan_repo=repo,
        clock=FixedClock(_now()),
    )
    return uc, position_repo


def test_match_uses_provided_job_id_filter() -> None:
    repo, _ = _run_and_detection(norm="JOB-SKU")
    pos_job = _position("pos-job", job_id="job-1", sku="JOB-SKU")
    pos_other = _position("pos-other", job_id="job-2", sku="OTHER")
    uc, position_repo = _use_case(
        repo=repo,
        aisle=_aisle(),
        positions=[pos_job, pos_other],
        products=[_product("pos-job", "JOB-SKU")],
        jobs=[_job("job-1"), _job("job-2")],
    )
    result = uc.execute(
        MatchAisleCodeScanDetectionsCommand(
            inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1"
        )
    )
    assert result.matched_count == 1
    assert position_repo.last_job_filter == "job-1"
    stored = repo.list_detections_for_run("run-1")[0]
    assert stored.matched_position_id == "pos-job"


def test_match_skips_when_no_result_context() -> None:
    repo, _ = _run_and_detection(norm="X")
    pos_scoped = _position("pos-1", job_id="job-1", sku="X")
    uc, _ = _use_case(
        repo=repo,
        aisle=_aisle(operational_job_id=None),
        positions=[pos_scoped],
        products=[_product("pos-1", "X")],
        jobs=[_job("job-1")],
    )
    result = uc.execute(
        MatchAisleCodeScanDetectionsCommand(inventory_id="inv-1", aisle_id="aisle-1")
    )
    assert result.warning_message == MISSING_RESULT_CONTEXT_WARNING
    assert result.matching_metadata["status"] == "skipped"
    stored = repo.list_detections_for_run("run-1")[0]
    assert stored.match_status == CodeScanMatchStatus.NOT_EVALUATED.value
    assert stored.matched_at is not None


def test_non_detected_gets_not_evaluated_with_matched_at() -> None:
    repo, _ = _run_and_detection(
        norm="X",
        detection_status=CodeScanDetectionStatus.DUPLICATE,
    )
    pos = _position("pos-1", job_id="job-1", sku="X")
    uc, _ = _use_case(
        repo=repo,
        aisle=_aisle(operational_job_id="job-1"),
        positions=[pos],
        products=[],
        jobs=[_job("job-1")],
    )
    uc.execute(
        MatchAisleCodeScanDetectionsCommand(
            inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1"
        )
    )
    stored = repo.list_detections_for_run("run-1")[0]
    assert stored.match_status == CodeScanMatchStatus.NOT_EVALUATED.value
    assert stored.matched_at is not None


def test_match_metadata_completed_shape() -> None:
    repo, _ = _run_and_detection(norm="3075807")
    pos = _position("pos-1", job_id="job-1", sku="3075807")
    uc, _ = _use_case(
        repo=repo,
        aisle=_aisle(operational_job_id="job-1"),
        positions=[pos],
        products=[_product("pos-1", "3075807")],
        jobs=[_job("job-1")],
    )
    result = uc.execute(
        MatchAisleCodeScanDetectionsCommand(
            inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1"
        )
    )
    assert result.matching_metadata["status"] == "completed"
    assert result.matching_metadata["scope"] == "job"
    assert result.matching_metadata["job_id"] == "job-1"
