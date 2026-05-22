"""Read-only review signals for the latest aisle code scan (Phase 6A)."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.code_scan_repository import CodeScanRepository
from src.application.ports.repositories import AisleRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.code_scan_review_signals import (
    CodeScanReviewSignal,
    CodeScanReviewSignalsSummary,
    build_review_signals,
    summarize_signals,
)
from src.domain.code_scans.entities import CodeScanRun


@dataclass(frozen=True)
class GetAisleCodeScanReviewSignalsCommand:
    inventory_id: str
    aisle_id: str


@dataclass(frozen=True)
class GetAisleCodeScanReviewSignalsResult:
    latest_run: CodeScanRun | None
    summary: CodeScanReviewSignalsSummary
    signals: tuple[CodeScanReviewSignal, ...]


class GetAisleCodeScanReviewSignalsUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        code_scan_repo: CodeScanRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._code_scan_repo = code_scan_repo

    def execute(
        self, command: GetAisleCodeScanReviewSignalsCommand
    ) -> GetAisleCodeScanReviewSignalsResult:
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )
        latest = self._code_scan_repo.get_latest_run_by_aisle(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
        )
        if latest is None:
            empty = summarize_signals(())
            return GetAisleCodeScanReviewSignalsResult(
                latest_run=None,
                summary=empty,
                signals=(),
            )

        detections = tuple(
            self._code_scan_repo.list_latest_detections_by_aisle(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
            )
        )
        signals = build_review_signals(detections=detections, latest_run=latest)
        summary = summarize_signals(signals, detections=detections)
        return GetAisleCodeScanReviewSignalsResult(
            latest_run=latest,
            summary=summary,
            signals=signals,
        )
