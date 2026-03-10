"""
Infrastructure service ports — v3.0 (Documento técnico §9.2).

ArtifactStorage: upload/store files. JobQueue: enqueue processing. AnalysisProvider: run analysis.
MetricsCalculator: compute inventory metrics. ResultMapper: map pipeline output to domain.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, BinaryIO, Dict, List

from src.application.ports.contracts import (
    AnalysisResultPayload,
    InventoryMetricsResult,
    MappedPositionPayload,
)


class ArtifactStorage(ABC):
    """Port for saving uploaded files (e.g. photos/videos). Returns storage path or URL."""

    @abstractmethod
    def save_file(self, path: str, file_obj: BinaryIO, content_type: str) -> str:
        ...


class JobQueue(ABC):
    """Port for enqueueing jobs. Returns job id from the queue. Payload for process_aisle: ProcessAislePayload."""

    @abstractmethod
    def enqueue(self, job_type: str, payload: Dict[str, Any]) -> str:
        ...


class AnalysisProvider(ABC):
    """Port for running analysis on an aisle's assets. Returns result per §9.4 (AnalysisResultPayload)."""

    @abstractmethod
    def analyze_aisle(self, aisle_id: str, asset_paths: List[str]) -> AnalysisResultPayload:
        ...


class MetricsCalculator(ABC):
    """Port for computing inventory metrics per Documento técnico §9.6. Returns InventoryMetricsResult."""

    @abstractmethod
    def calculate_inventory_metrics(self, inventory_id: str) -> InventoryMetricsResult:
        ...


class ResultMapper(ABC):
    """
    Port for mapping pipeline output (§9.4) to domain structures.
    Returns list of MappedPositionPayload (each may include products and evidence refs).
    """

    @abstractmethod
    def map_analysis_to_positions(
        self, aisle_id: str, analysis_result: AnalysisResultPayload
    ) -> List[MappedPositionPayload]:
        """Return list of position payloads (each may include products and evidence refs)."""
        ...
