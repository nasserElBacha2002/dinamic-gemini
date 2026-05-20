"""Tests for GetPositionCodeScanEvidenceUseCase (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    PositionNotFoundError,
)
from src.application.use_cases.get_position_code_scan_evidence import (
    GetPositionCodeScanEvidenceCommand,
    GetPositionCodeScanEvidenceUseCase,
)
from src.domain.aisle.entities import Aisle
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.domain.code_scans.matching import CodeScanMatchStatus, CodeScanMatchType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position
from src.infrastructure.repositories.memory_code_scan_repository import MemoryCodeScanRepository
from tests.application.use_cases.test_match_aisle_code_scan_detections import (
    StubPositionRepo,
    _aisle,
    _position,
)
from tests.application.use_cases.test_run_aisle_code_scan import StubAisleRepo

NOW = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


class StubInventoryRepo:
    def __init__(self, exists: bool = True) -> None:
        self._exists = exists

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        if not self._exists:
            return None
        return Inventory(
            id=inventory_id,
            name="Inv",
            status=InventoryStatus.IN_REVIEW,
            created_at=NOW,
            updated_at=NOW,
            client_id="c1",
        )


def _run(run_id: str = "run-1") -> CodeScanRun:
    return CodeScanRun(
        id=run_id,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        status=CodeScanRunStatus.COMPLETED,
        is_latest=True,
        total_assets=1,
        processed_assets=1,
        failed_assets=0,
        total_codes_found=2,
        total_qr_found=1,
        total_barcodes_found=1,
        started_at=NOW,
        finished_at=NOW,
        scanner_engine="pyzbar",
        created_by="admin",
    )


def _det(
    det_id: str,
    *,
    matched_position_id: str | None = None,
    match_type: str | None = None,
) -> CodeScanDetection:
    return CodeScanDetection(
        id=det_id,
        run_id="run-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        asset_id=f"asset-{det_id}",
        code_type=CodeType.BARCODE,
        code_value="7791234567890",
        normalized_code_value="7791234567890",
        detection_status=CodeScanDetectionStatus.DETECTED,
        scanner_engine="pyzbar",
        created_at=NOW,
        matched_position_id=matched_position_id,
        match_status=CodeScanMatchStatus.MATCHED if matched_position_id else None,
        match_type=match_type,
        match_confidence=1.0 if matched_position_id else None,
        matched_at=NOW if matched_position_id else None,
    )


def _use_case(
    *,
    positions: list[Position] | None = None,
    repo: MemoryCodeScanRepository | None = None,
    inventory_exists: bool = True,
    aisle: Aisle | None = None,
) -> GetPositionCodeScanEvidenceUseCase:
    pos = positions or [_position("pos-1")]
    aisle_row = aisle if aisle is not None else _aisle()
    return GetPositionCodeScanEvidenceUseCase(
        inventory_repo=StubInventoryRepo(inventory_exists),
        aisle_repo=StubAisleRepo(aisle_row),
        position_repo=StubPositionRepo(pos),
        code_scan_repo=repo or MemoryCodeScanRepository(),
    )


def test_inventory_not_found() -> None:
    uc = _use_case(inventory_exists=False)
    with pytest.raises(InventoryNotFoundError):
        uc.execute(
            GetPositionCodeScanEvidenceCommand("missing", "aisle-1", "pos-1")
        )


def test_aisle_not_found() -> None:
    uc = _use_case(aisle=_aisle())
    with pytest.raises(AisleNotFoundError):
        uc.execute(GetPositionCodeScanEvidenceCommand("inv-1", "missing-aisle", "pos-1"))


def test_position_not_found() -> None:
    uc = _use_case(positions=[_position("pos-1")])
    with pytest.raises(PositionNotFoundError):
        uc.execute(GetPositionCodeScanEvidenceCommand("inv-1", "aisle-1", "missing-pos"))


def test_position_wrong_aisle() -> None:
    wrong = _position("pos-1")
    wrong.aisle_id = "other-aisle"
    uc = _use_case(positions=[wrong])
    with pytest.raises(PositionNotFoundError):
        uc.execute(GetPositionCodeScanEvidenceCommand("inv-1", "aisle-1", "pos-1"))


def test_no_latest_run_returns_empty() -> None:
    result = _use_case().execute(
        GetPositionCodeScanEvidenceCommand("inv-1", "aisle-1", "pos-1")
    )
    assert result.latest_run is None
    assert result.detections == ()
    assert result.summary.total_detections == 0


def test_latest_run_no_matched_detections_for_position() -> None:
    repo = MemoryCodeScanRepository()
    repo.save_run(_run())
    repo.save_detections([_det("d1", matched_position_id="other-pos")])
    result = _use_case(repo=repo).execute(
        GetPositionCodeScanEvidenceCommand("inv-1", "aisle-1", "pos-1")
    )
    assert result.latest_run is not None
    assert result.detections == ()
    assert result.summary.total_detections == 0


def test_returns_only_matched_detections_for_position() -> None:
    repo = MemoryCodeScanRepository()
    repo.save_run(_run())
    repo.save_detections(
        [
            _det("d1", matched_position_id="pos-1", match_type=CodeScanMatchType.SKU_EXACT),
            _det("d2", matched_position_id="pos-2"),
            _det("d3", matched_position_id="pos-1", match_type=CodeScanMatchType.BARCODE_EXACT),
        ]
    )
    result = _use_case(repo=repo).execute(
        GetPositionCodeScanEvidenceCommand("inv-1", "aisle-1", "pos-1")
    )
    assert len(result.detections) == 2
    assert {d.id for d in result.detections} == {"d1", "d3"}
    assert result.summary.total_detections == 2
    assert result.summary.source_assets_count == 2
    assert all(d.asset_id for d in result.detections)
    assert all(d.match_type for d in result.detections)


def test_repo_list_latest_by_matched_position() -> None:
    repo = MemoryCodeScanRepository()
    repo.save_run(_run())
    repo.save_detections([_det("d1", matched_position_id="pos-1")])
    rows = repo.list_latest_detections_by_matched_position(
        inventory_id="inv-1", aisle_id="aisle-1", position_id="pos-1"
    )
    assert len(rows) == 1
    assert rows[0].id == "d1"
