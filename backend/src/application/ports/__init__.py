"""
Application ports — v3.0 (Documento técnico §9.1, §9.2).

Repositories and infrastructure service contracts. Use cases depend on these abstractions.
"""

from src.application.ports.clock import Clock
from src.application.ports.contracts import (
    AnalysisResultPayload,
    InventoryMetricsResult,
    MappedPositionPayload,
    PositionListQuery,
    ProcessAislePayload,
    ProductItemPayload,
)
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
    SourceAssetRepository,
)
from src.application.ports.services import (
    AnalysisProvider,
    ArtifactStorage,
    JobQueue,
    MetricsCalculator,
    ResultMapper,
)

__all__ = [
    "AnalysisResultPayload",
    "AnalysisProvider",
    "ArtifactStorage",
    "AisleRepository",
    "Clock",
    "EvidenceRepository",
    "InventoryMetricsResult",
    "InventoryRepository",
    "JobQueue",
    "JobRepository",
    "MappedPositionPayload",
    "MetricsCalculator",
    "PositionListQuery",
    "PositionRepository",
    "ProcessAislePayload",
    "ProductItemPayload",
    "ProductRecordRepository",
    "ResultMapper",
    "ReviewActionRepository",
    "SourceAssetRepository",
]
