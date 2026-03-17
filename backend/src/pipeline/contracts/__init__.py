"""Pipeline contracts. v2.3.A: PipelineStage protocol; v3.2.4: AnalysisContext."""

from src.pipeline.contracts.stage import PipelineStage
from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    AnalysisImage,
    VisualReferenceContext,
)

__all__ = [
    "PipelineStage",
    "AnalysisContext",
    "AnalysisImage",
    "VisualReferenceContext",
]
