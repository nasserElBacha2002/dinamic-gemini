"""List detections from the latest aisle code scan run."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.code_scan_repository import CodeScanRepository
from src.application.ports.repositories import AisleRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.code_scans.entities import CodeScanDetection, CodeScanRun


@dataclass(frozen=True)
class ListAisleCodeScansCommand:
    inventory_id: str
    aisle_id: str


@dataclass(frozen=True)
class ListAisleCodeScansResult:
    latest_run: CodeScanRun | None
    detections: tuple[CodeScanDetection, ...]


class ListAisleCodeScansUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        code_scan_repo: CodeScanRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._code_scan_repo = code_scan_repo

    def execute(self, command: ListAisleCodeScansCommand) -> ListAisleCodeScansResult:
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
            return ListAisleCodeScansResult(latest_run=None, detections=())
        rows = self._code_scan_repo.list_detections_for_run(latest.id)
        return ListAisleCodeScansResult(latest_run=latest, detections=tuple(rows))
