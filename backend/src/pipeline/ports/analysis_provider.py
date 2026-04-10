"""
AnalysisProvider port — global product analysis (Stage 2.3.B).

The hybrid pipeline depends on this interface only (not on vendor SDKs). Implementations are
strategies that call a registry-resolved ``LlmGlobalAnalysisExecutor``. Contract matches the
v2.1/v2.3 hybrid flow (single global entity analysis call, parsed JSON for entity resolution).
v3.2.4 Phase 4: provider capabilities and provider_metadata for visual reference consumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import numpy as np

from src.pipeline.context.run_context import RunContext


# v3.2.4 Phase 4: provider capability flags
PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE = "visual_references_available"
PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED = "visual_references_consumed"
PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT = "visual_reference_count"
PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS = "visual_reference_ids"


@dataclass
class ProviderCapabilities:
    """Declares what analysis context features a provider supports (v3.2.4 Phase 4)."""

    supports_visual_reference_context: bool = False


@dataclass
class AnalysisResult:
    """
    Structured result of global analysis (v2.1 entity detection).

    Intentionally minimal for Stage B. It currently carries only the parsed payload consumed
    by the existing pipeline (parse_entities). Future stages may extend it with metadata such
    as raw response, tokens, latency, model info, or trace IDs.
    v3.2.4 Phase 4: provider_metadata carries visual reference usage (available/consumed/count).
    Phase 6: optional ``prompt_composition`` — same dict attached to ``LLMRequest.metadata`` for
    this call (full prompt text for job-level audit). Execution logs use a redacted subset; see
    ``prompt_traceability`` module docstring.
    """

    parsed_json: Dict[str, Any]
    provider_name: str
    provider_metadata: Optional[Dict[str, Any]] = None
    prompt_composition: Optional[Dict[str, Any]] = None


class AnalysisProvider(Protocol):
    """Port for performing global analysis on frames. Implementations wrap LLM providers."""

    def get_capabilities(self) -> ProviderCapabilities:
        """Return provider capabilities (e.g. supports_visual_reference_context). Default: no extras."""
        ...

    def analyze(
        self,
        context: RunContext,
        frames_nd: List[np.ndarray],
        frame_paths: List[Path],
        frame_refs: List[str],
        metadata: Dict[str, Any],
    ) -> AnalysisResult:
        """
        Run global analysis; return parsed v2.1 JSON and provider name.

        Args:
            context: Run context (settings, logger, job_id, etc.).
            frames_nd: Frames in memory (BGR ndarray).
            frame_paths: Paths to frame images (for providers that need paths).
            frame_refs: Reference identifiers per frame.
            metadata: Bundle metadata (frame_count, source, frame_indices, etc.).

        Returns:
            AnalysisResult with parsed_json (v2.1 schema) and provider_name.
        """
        ...
