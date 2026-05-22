"""Export latest aisle code scan data as CSV (Phase 6B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.application.errors import (
    CodeScanExportNoRunError,
    CodeScanExportUnsupportedFormatError,
    CodeScanExportUnsupportedTypeError,
)
from src.application.ports.code_scan_repository import CodeScanRepository
from src.application.ports.repositories import AisleRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.code_scan_csv_exporter import (
    build_detections_csv,
    build_summary_csv,
    build_unmatched_csv,
    code_scan_export_filename,
)

ExportFormat = Literal["csv"]
ExportType = Literal["detections", "unmatched", "summary"]


@dataclass(frozen=True)
class ExportAisleCodeScansCommand:
    inventory_id: str
    aisle_id: str
    export_format: str
    export_type: str


@dataclass(frozen=True)
class ExportAisleCodeScansResult:
    filename: str
    body: str


class ExportAisleCodeScansUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        code_scan_repo: CodeScanRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._code_scan_repo = code_scan_repo

    def execute(self, command: ExportAisleCodeScansCommand) -> ExportAisleCodeScansResult:
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )

        fmt = (command.export_format or "").strip().lower()
        if fmt != "csv":
            raise CodeScanExportUnsupportedFormatError(
                f"Unsupported export format: {command.export_format!r}"
            )

        export_type = (command.export_type or "").strip().lower()
        if export_type not in ("detections", "unmatched", "summary"):
            raise CodeScanExportUnsupportedTypeError(
                f"Unsupported export type: {command.export_type!r}"
            )

        latest = self._code_scan_repo.get_latest_run_by_aisle(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
        )
        if latest is None:
            raise CodeScanExportNoRunError(
                f"No code scan run for aisle {command.aisle_id}; run a scan before exporting."
            )

        filename = code_scan_export_filename(
            command.inventory_id, command.aisle_id, export_type
        )

        if export_type == "detections":
            detections = self._code_scan_repo.list_latest_detections_by_aisle(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
            )
            body = build_detections_csv(run=latest, detections=detections)
        elif export_type == "unmatched":
            detections = self._code_scan_repo.list_latest_detections_by_aisle(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
            )
            body = build_unmatched_csv(run=latest, detections=detections)
        else:
            items = self._code_scan_repo.summarize_latest_detections_by_aisle(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
            )
            body = build_summary_csv(run=latest, items=items)

        return ExportAisleCodeScansResult(filename=filename, body=body)
