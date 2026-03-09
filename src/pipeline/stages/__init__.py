"""Pipeline stages. v2.3.A: InputPreparationStage; v2.3.C: FrameAcquisition, Analysis, EntityResolution, Evidence, Reporting."""

from src.pipeline.stages.input_preparation_stage import InputPreparationStage, PreparedInput
from src.pipeline.stages.frame_acquisition_stage import FrameAcquisitionStage, AcquiredFrames
from src.pipeline.stages.analysis_stage import AnalysisStage, AnalysisStageResult
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage, ResolvedEntities
from src.pipeline.stages.evidence_stage import EvidenceStage, EvidenceStageInput, EvidenceArtifacts
from src.pipeline.stages.reporting_stage import ReportingStage, ReportingStageInput, ReportingResult

__all__ = [
    "InputPreparationStage",
    "PreparedInput",
    "FrameAcquisitionStage",
    "AcquiredFrames",
    "AnalysisStage",
    "AnalysisStageResult",
    "EntityResolutionStage",
    "ResolvedEntities",
    "EvidenceStage",
    "EvidenceStageInput",
    "EvidenceArtifacts",
    "ReportingStage",
    "ReportingStageInput",
    "ReportingResult",
]
