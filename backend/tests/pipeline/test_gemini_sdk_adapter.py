"""Phase 4 — Gemini SDK adapter isolates vendor errors as LLMProviderError."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.exceptions.global_analysis_exceptions import GlobalAnalysisParsingError
from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest
from src.llm.gemini_sdk_adapter import GeminiSdkAdapter


def _settings_with_key() -> MagicMock:
    s = MagicMock()
    s.gemini_api_key = "k"
    s.gemini_model_name = "gemini-2.0-flash-exp"
    s.gemini_max_retries = 1
    s.gemini_retry_delay = 0.01
    s.hybrid_prompt = "global_v21"
    return s


def test_gemini_sdk_adapter_maps_global_analysis_parsing_error() -> None:
    adapter = GeminiSdkAdapter()
    settings = _settings_with_key()
    frames = [np.zeros((8, 8, 3), dtype=np.uint8)]
    req = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=frames,
    )
    with patch("src.llm.gemini_sdk_adapter.GeminiGlobalAnalyzer") as analyzer_cls:
        inst = MagicMock()
        inst.analyze_video_frames.side_effect = GlobalAnalysisParsingError("bad json")
        analyzer_cls.return_value = inst
        with pytest.raises(LLMProviderError) as ei:
            adapter.execute(req, settings)
        assert ei.value.code == "INVALID_JSON"


def test_gemini_sdk_adapter_not_configured_without_api_key() -> None:
    adapter = GeminiSdkAdapter()
    settings = MagicMock()
    settings.gemini_api_key = ""
    req = LLMRequest(
        job_id="j1",
        frames=[Path("/nope.jpg")],
        frame_refs=[],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(req, settings)
    assert ei.value.code == "NOT_CONFIGURED"
