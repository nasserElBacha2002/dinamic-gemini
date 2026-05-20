"""Read code scan detections linked to a position (Phase 5 evidence enrichment)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.application.ports.code_scan_repository import CodeScanRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
)
from src.application.use_cases.review_validation import resolve_position
from src.domain.code_scans.entities import CodeScanDetection, CodeScanRun


@dataclass(frozen=True)
class GetPositionCodeScanEvidenceCommand:
    inventory_id: str
    aisle_id: str
    position_id: str


@dataclass(frozen=True)
class PositionCodeScanEvidenceSummary:
    total_detections: int
    source_assets_count: int
    code_types: dict[str, int]


@dataclass(frozen=True)
class GetPositionCodeScanEvidenceResult:
    latest_run: CodeScanRun | None
    detections: tuple[CodeScanDetection, ...]
    summary: PositionCodeScanEvidenceSummary


def _build_summary(detections: tuple[CodeScanDetection, ...]) -> PositionCodeScanEvidenceSummary:
    asset_ids = tuple(dict.fromkeys(d.asset_id for d in detections))
    type_counts: Counter[str] = Counter()
    for d in detections:
        type_counts[d.code_type.value] += 1
    return PositionCodeScanEvidenceSummary(
        total_detections=len(detections),
        source_assets_count=len(asset_ids),
        code_types=dict(type_counts),
    )


class GetPositionCodeScanEvidenceUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        code_scan_repo: CodeScanRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._code_scan_repo = code_scan_repo

    def execute(
        self, command: GetPositionCodeScanEvidenceCommand
    ) -> GetPositionCodeScanEvidenceResult:
        resolve_position(
            self._inventory_repo,
            self._aisle_repo,
            self._position_repo,
            command.inventory_id,
            command.aisle_id,
            command.position_id,
        )
        latest = self._code_scan_repo.get_latest_run_by_aisle(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
        )
        if latest is None:
            return GetPositionCodeScanEvidenceResult(
                latest_run=None,
                detections=(),
                summary=PositionCodeScanEvidenceSummary(
                    total_detections=0,
                    source_assets_count=0,
                    code_types={},
                ),
            )

        matched = self._code_scan_repo.list_latest_detections_by_matched_position(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            position_id=command.position_id,
        )
        detections = tuple(matched)
        return GetPositionCodeScanEvidenceResult(
            latest_run=latest,
            detections=detections,
            summary=_build_summary(detections),
        )
