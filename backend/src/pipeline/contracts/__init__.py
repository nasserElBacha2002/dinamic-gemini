"""Pipeline contracts. v2.3.A: PipelineStage protocol; v3.2.4: AnalysisContext."""

from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    AnalysisImage,
    VisualReferenceContext,
    analysis_context_from_dict,
    analysis_context_to_dict,
)
from src.pipeline.contracts.stage import PipelineStage

__all__ = [
    "AnalysisContext",
    "AnalysisImage",
    "PipelineStage",
    "VisualReferenceContext",
    "analysis_context_from_dict",
    "analysis_context_to_dict",
]
