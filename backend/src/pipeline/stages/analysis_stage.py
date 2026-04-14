"""
AnalysisStage — delegate to AnalysisProvider and return structured result (v2.3.C).

Performs the global analysis call only; no entity parsing.
v3.2.4 Phase 4: passes through provider_metadata (visual reference usage) for callers to persist.
Phase 5: normalizes ``parsed_json`` (e.g. OpenAI quantity aliases) before entity resolution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.llm.normalization.entity_normalizer import normalize_llm_response
from src.pipeline.ports.analysis_provider import AnalysisProvider, AnalysisResult
from src.pipeline.stages.frame_acquisition_stage import AcquiredFrames
from src.pipeline.context.run_context import RunContext


@dataclass
class AnalysisStageResult:
    """Output of AnalysisStage: parsed analysis payload for entity resolution."""

    parsed_json: Dict[str, Any]
    provider_name: str
    provider_metadata: Optional[Dict[str, Any]] = None
    # Phase 6: pass-through of AnalysisResult.prompt_composition for run_metadata persistence.
    prompt_composition: Optional[Dict[str, Any]] = None
    # Phase 9: pass-through of provider-agnostic usage+pricing snapshot for run_metadata persistence.
    llm_cost_snapshot: Optional[Dict[str, Any]] = None


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
        parsed = normalize_llm_response(result.parsed_json, result.provider_name)
        log = getattr(context, "logger", None)
        if log is not None and log.isEnabledFor(logging.DEBUG):
            ents = parsed.get("entities")
            if isinstance(ents, list):
                with_plq = sum(
                    1
                    for e in ents
                    if isinstance(e, dict) and e.get("product_label_quantity") is not None
                )
                log.debug(
                    "analysis_stage post_normalize: provider=%s entities=%d product_label_quantity_set=%d",
                    result.provider_name,
                    len(ents),
                    with_plq,
                )
        return AnalysisStageResult(
            parsed_json=parsed,
            provider_name=result.provider_name,
            provider_metadata=result.provider_metadata,
            prompt_composition=result.prompt_composition,
            llm_cost_snapshot=result.llm_cost_snapshot,
        )
