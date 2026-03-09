"""
GeminiAnalysisProvider — adapter implementing AnalysisProvider (Stage 2.3.B).

In Stage B this adapter wraps the current global entity analysis flow only. It preserves the
existing prompt (GLOBAL_ENTITY_ANALYSIS_PROMPT_V21), schema (v2.1), and parse contract. It is
not yet a general-purpose Gemini abstraction; future stages may introduce a broader provider
or multiple analysis flows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from src.llm.prompts import get_hybrid_prompt
from src.llm.providers.factory import get_llm_provider
from src.llm.types import LLMRequest
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import AnalysisResult


class GeminiAnalysisProvider:
    """
    Implements AnalysisProvider by delegating to the current LLM provider (Gemini/Fake/OpenAI).

    Wraps the existing global entity analysis flow: same prompt, schema, and parse contract.
    Not a general-purpose Gemini adapter; scope is intentionally aligned with v2.1/v2.3 hybrid analysis.
    """

    def analyze(
        self,
        context: RunContext,
        frames_nd: List[np.ndarray],
        frame_paths: List[Path],
        frame_refs: List[str],
        metadata: Dict[str, Any],
    ) -> AnalysisResult:
        """Build LLMRequest, call get_llm_provider(settings).analyze_global, return AnalysisResult."""
        settings = context.settings
        job_id = context.job_id
        provider = get_llm_provider(settings)
        prompt_text = get_hybrid_prompt(getattr(settings, "hybrid_prompt", "global_v21"))
        request = LLMRequest(
            job_id=job_id,
            frames=frame_paths,
            frame_refs=frame_refs,
            prompt=prompt_text,
            schema_version="v2.1",
            metadata=metadata,
            frames_nd=frames_nd,
        )
        response = provider.analyze_global(request)
        return AnalysisResult(
            parsed_json=response.parsed_json,
            provider_name=response.provider,
        )
