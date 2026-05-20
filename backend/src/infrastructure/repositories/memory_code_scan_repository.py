"""In-memory CodeScanRepository for tests and SQL fallback mode."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from src.application.ports.code_scan_repository import CodeScanRepository, CodeScanSummaryItem
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
)


class MemoryCodeScanRepository(CodeScanRepository):
    def __init__(self) -> None:
        self._runs: dict[str, CodeScanRun] = {}
        self._detections: dict[str, CodeScanDetection] = {}

    def create_run(self, run: CodeScanRun) -> None:
        self._runs[run.id] = run

    def mark_previous_runs_not_latest(self, *, inventory_id: str, aisle_id: str) -> None:
        for run in self._runs.values():
            if (
                run.inventory_id == inventory_id
                and run.aisle_id == aisle_id
                and run.is_latest
            ):
                run.is_latest = False

    def save_run(self, run: CodeScanRun) -> None:
        self._runs[run.id] = run

    def save_detections(self, detections: Sequence[CodeScanDetection]) -> None:
        for d in detections:
            self._detections[d.id] = d

    def get_latest_run_by_aisle(self, *, inventory_id: str, aisle_id: str) -> CodeScanRun | None:
        latest: CodeScanRun | None = None
        for run in self._runs.values():
            if (
                run.inventory_id == inventory_id
                and run.aisle_id == aisle_id
                and run.is_latest
            ):
                if latest is None or run.started_at > latest.started_at:
                    latest = run
        return latest

    def list_detections_for_run(self, run_id: str) -> Sequence[CodeScanDetection]:
        return [d for d in self._detections.values() if d.run_id == run_id]

    def list_latest_detections_by_aisle(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[CodeScanDetection]:
        run = self.get_latest_run_by_aisle(inventory_id=inventory_id, aisle_id=aisle_id)
        if run is None:
            return []
        return self.list_detections_for_run(run.id)

    def summarize_latest_detections_by_aisle(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[CodeScanSummaryItem]:
        detections = self.list_latest_detections_by_aisle(
            inventory_id=inventory_id, aisle_id=aisle_id
        )
        groups: dict[tuple[str, str], list[CodeScanDetection]] = defaultdict(list)
        for d in detections:
            if d.detection_status == CodeScanDetectionStatus.ERROR:
                continue
            key = (d.normalized_code_value, d.code_type.value)
            groups[key].append(d)

        items: list[CodeScanSummaryItem] = []
        for (norm, code_type), rows in groups.items():
            asset_ids = tuple(dict.fromkeys(r.asset_id for r in rows))
            first_seen = min(r.created_at for r in rows)
            items.append(
                CodeScanSummaryItem(
                    code_value=rows[0].code_value,
                    normalized_code_value=norm,
                    code_type=code_type,
                    occurrences=len(rows),
                    asset_ids=asset_ids,
                    first_seen_at=first_seen,
                )
            )
        items.sort(key=lambda x: (x.normalized_code_value, x.code_type))
        return items
