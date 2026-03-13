"""
AnalysisProvider port — global product analysis (Stage 2.3.B).

Pipeline depends on this interface; implementations (Gemini, Fake, etc.) are adapters. The
current contract is aligned with the existing v2.1/v2.3 hybrid analysis flow (single global
entity analysis call, parsed JSON consumed by parse_entities).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Protocol

import numpy as np

from src.pipeline.context.run_context import RunContext


@dataclass
class AnalysisResult:
    """
    Structured result of global analysis (v2.1 entity detection).

    Intentionally minimal for Stage B. It currently carries only the parsed payload consumed
    by the existing pipeline (parse_entities). Future stages may extend it with metadata such
    as raw response, tokens, latency, model info, or trace IDs.
    """

    parsed_json: Dict[str, Any]
    provider_name: str


class AnalysisProvider(Protocol):
    """Port for performing global analysis on frames. Implementations wrap LLM providers."""

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
