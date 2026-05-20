"""Tests for MatchAisleCodeScanDetectionsUseCase (Phase 4 read-only matching)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import (
    JOB_ID_FILTER_UNSET,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.use_cases.match_aisle_code_scan_detections import (
    MatchAisleCodeScanDetectionsCommand,
    MatchAisleCodeScanDetectionsUseCase,
)
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.domain.code_scans.matching import CodeScanMatchStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_code_scan_repository import MemoryCodeScanRepository
from tests.application.use_cases.test_run_aisle_code_scan import FixedClock, StubAisleRepo, _aisle


class StubPositionRepo(PositionRepository):
    def __init__(self, positions: Sequence[Position]) -> None:
        self._positions = list(positions)

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
        rows = [p for p in self._positions if p.aisle_id == aisle_id]
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


def _now() -> datetime:
    return datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def _run_and_detection(
    *,
    norm: str,
    detection_id: str = "d1",
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
                detection_status=CodeScanDetectionStatus.DETECTED,
                scanner_engine="fake",
                created_at=now,
            )
        ]
    )
    return repo, detection_id


def _position(position_id: str, *, sku: str | None = None, barcode: str | None = None) -> Position:
    now = _now()
    summary = {}
    if barcode:
        summary["position_barcode"] = barcode
    products = []
    if sku:
        products.append(
            ProductRecord(
                id=f"prod-{position_id}",
                position_id=position_id,
                sku=sku,
                detected_quantity=1,
                confidence=0.9,
                created_at=now,
                updated_at=now,
            )
        )
    return (
        Position(
            id=position_id,
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=True,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json=summary or None,
        ),
        products,
    )


def _use_case(
    *,
    repo: MemoryCodeScanRepository,
    positions: Sequence[Position],
    products: Sequence[ProductRecord],
) -> MatchAisleCodeScanDetectionsUseCase:
    return MatchAisleCodeScanDetectionsUseCase(
        aisle_repo=StubAisleRepo(_aisle()),
        position_repo=StubPositionRepo(positions),
        product_record_repo=StubProductRepo(products),
        code_scan_repo=repo,
        clock=FixedClock(_now()),
    )


def test_match_persists_sku_exact() -> None:
    repo, det_id = _run_and_detection(norm="3075807")
    pos, prods = _position("pos-1", sku="3075807")
    uc = _use_case(repo=repo, positions=[pos], products=prods)
    result = uc.execute(
        MatchAisleCodeScanDetectionsCommand(inventory_id="inv-1", aisle_id="aisle-1")
    )
    assert result.matched_count == 1
    stored = repo.list_detections_for_run("run-1")[0]
    assert stored.match_status == CodeScanMatchStatus.MATCHED.value
    assert stored.matched_position_id == "pos-1"
    assert stored.id == det_id


def test_match_does_not_modify_position_or_product() -> None:
    repo, _ = _run_and_detection(norm="3075807")
    pos, prods = _position("pos-1", sku="3075807")
    pos_before = pos
    prod_before = prods[0]
    product_repo = StubProductRepo(prods)
    uc = MatchAisleCodeScanDetectionsUseCase(
        aisle_repo=StubAisleRepo(_aisle()),
        position_repo=StubPositionRepo([pos]),
        product_record_repo=product_repo,
        code_scan_repo=repo,
        clock=FixedClock(_now()),
    )
    uc.execute(MatchAisleCodeScanDetectionsCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert product_repo.saved == []
    assert pos == pos_before
    assert prods[0] == prod_before
    assert pos.review_resolution is None


def test_match_no_match_status() -> None:
    repo, _ = _run_and_detection(norm="UNKNOWN-CODE")
    pos, prods = _position("pos-1", sku="OTHER")
    uc = _use_case(repo=repo, positions=[pos], products=prods)
    result = uc.execute(
        MatchAisleCodeScanDetectionsCommand(inventory_id="inv-1", aisle_id="aisle-1")
    )
    assert result.no_match_count == 1
    assert repo.list_detections_for_run("run-1")[0].match_status == CodeScanMatchStatus.NO_MATCH.value
