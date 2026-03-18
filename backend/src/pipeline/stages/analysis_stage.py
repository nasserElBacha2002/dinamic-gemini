"""
AnalysisStage — delegate to AnalysisProvider and return structured result (v2.3.C).

Performs the global analysis call only; no entity parsing.
v3.2.4 Phase 4: passes through provider_metadata (visual reference usage) for callers to persist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.pipeline.ports.analysis_provider import AnalysisProvider, AnalysisResult
from src.pipeline.stages.frame_acquisition_stage import AcquiredFrames
from src.pipeline.context.run_context import RunContext


@dataclass
class AnalysisStageResult:
    """Output of AnalysisStage: parsed analysis payload for entity resolution."""

    parsed_json: Dict[str, Any]
    provider_name: str
    provider_metadata: Optional[Dict[str, Any]] = None


class AnalysisStage:
    """Stage: call AnalysisProvider.analyze and return result; progress is caller's responsibility."""

    def __init__(self, analysis_provider: AnalysisProvider) -> None:
        self._analysis_provider = analysis_provider

    def run(self, context: RunContext, data: AcquiredFrames) -> AnalysisStageResult:
        """
        Invoke analysis provider; return parsed JSON and provider name.

        Raises:
            LLMProviderError (from provider): When the provider fails (caller maps to exit code 1).
        """
        result: AnalysisResult = self._analysis_provider.analyze(
            context,
            data.frames_nd,
            data.frame_paths,
            data.frame_refs,
            data.metadata,
        )
        return AnalysisStageResult(
            parsed_json=result.parsed_json,
            provider_name=result.provider_name,
            provider_metadata=result.provider_metadata,
        )
