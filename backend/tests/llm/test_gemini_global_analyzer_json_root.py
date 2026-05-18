"""B2.5 — Gemini global analyzer rejects non-object JSON roots."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.exceptions.global_analysis_exceptions import GlobalAnalysisParsingError
from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer


def test_gemini_analyzer_rejects_json_array_root() -> None:
    """Valid JSON array must fail before schema validation (pipeline expects object root)."""
    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = "[1, 2, 3]"
    analyzer = GeminiGlobalAnalyzer(mock_client)
    frame = [np.zeros((16, 16, 3), dtype=np.uint8)]

    with pytest.raises(GlobalAnalysisParsingError, match="JSON object"):
        analyzer.analyze_video_frames(frame, frame_refs=["frame_0"])


def test_gemini_analyzer_rejects_json_string_root() -> None:
    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = '"only-a-string"'
    analyzer = GeminiGlobalAnalyzer(mock_client)
    frame = [np.zeros((16, 16, 3), dtype=np.uint8)]

    with pytest.raises(GlobalAnalysisParsingError, match="JSON object"):
        analyzer.analyze_video_frames(frame, frame_refs=["frame_0"])
