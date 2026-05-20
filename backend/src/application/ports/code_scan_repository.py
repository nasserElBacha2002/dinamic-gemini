"""Repository port for aisle code scan runs and detections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src.domain.code_scans.entities import CodeScanDetection, CodeScanRun


@dataclass(frozen=True)
class CodeScanSummaryItem:
    code_value: str
    normalized_code_value: str
    code_type: str
    occurrences: int
    asset_ids: tuple[str, ...]
    first_seen_at: datetime
    match_status: str | None = None
    matched_position_ids: tuple[str, ...] = ()
    match_types: tuple[str, ...] = ()
    match_status_counts: dict[str, int] | None = None


class CodeScanRepository(ABC):
    @abstractmethod
    def replace_latest_run(self, run: CodeScanRun) -> None:
        """Atomically clear previous latest for the aisle scope and insert ``run`` as latest."""

    @abstractmethod
    def save_run(self, run: CodeScanRun) -> None: ...

    @abstractmethod
    def save_detections(self, detections: Sequence[CodeScanDetection]) -> None: ...

    @abstractmethod
    def get_latest_run_by_aisle(self, *, inventory_id: str, aisle_id: str) -> CodeScanRun | None: ...

    @abstractmethod
    def list_detections_for_run(self, run_id: str) -> Sequence[CodeScanDetection]: ...

    @abstractmethod
    def list_latest_detections_by_aisle(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[CodeScanDetection]: ...

    @abstractmethod
    def summarize_latest_detections_by_aisle(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[CodeScanSummaryItem]: ...

    @abstractmethod
    def update_detection_matches(self, detections: Sequence[CodeScanDetection]) -> None:
        """Persist read-only match fields on existing detection rows."""
        ...
