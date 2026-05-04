"""Pipeline stages. v2.3.A: InputPreparationStage; v2.3.C: FrameAcquisition, Analysis, EntityResolution, Evidence, Reporting."""

from src.pipeline.stages.analysis_stage import AnalysisStage, AnalysisStageResult
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage, ResolvedEntities
from src.pipeline.stages.evidence_stage import EvidenceArtifacts, EvidenceStage, EvidenceStageInput
from src.pipeline.stages.frame_acquisition_stage import AcquiredFrames, FrameAcquisitionStage
from src.pipeline.stages.input_preparation_stage import InputPreparationStage, PreparedInput
from src.pipeline.stages.reporting_stage import ReportingResult, ReportingStage, ReportingStageInput

__all__ = [
    "AcquiredFrames",
    "AnalysisStage",
    "AnalysisStageResult",
    "EntityResolutionStage",
    "EvidenceArtifacts",
    "EvidenceStage",
    "EvidenceStageInput",
    "FrameAcquisitionStage",
    "InputPreparationStage",
    "PreparedInput",
    "ReportingResult",
    "ReportingStage",
    "ReportingStageInput",
    "ResolvedEntities",
]
