"""Summarize grouped detections from the latest aisle code scan run."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.code_scan_repository import CodeScanRepository, CodeScanSummaryItem
from src.application.ports.repositories import AisleRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.code_scans.entities import CodeScanRun


@dataclass(frozen=True)
class SummarizeAisleCodeScansCommand:
    inventory_id: str
    aisle_id: str


@dataclass(frozen=True)
class SummarizeAisleCodeScansResult:
    latest_run: CodeScanRun | None
    items: tuple[CodeScanSummaryItem, ...]


class SummarizeAisleCodeScansUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        code_scan_repo: CodeScanRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._code_scan_repo = code_scan_repo

    def execute(self, command: SummarizeAisleCodeScansCommand) -> SummarizeAisleCodeScansResult:
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
            return SummarizeAisleCodeScansResult(latest_run=None, items=())
        items = self._code_scan_repo.summarize_latest_detections_by_aisle(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
        )
        return SummarizeAisleCodeScansResult(latest_run=latest, items=tuple(items))
