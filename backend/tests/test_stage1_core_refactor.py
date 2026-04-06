"""
Stage 1 — Core pipeline (v2.2: hybrid only).

Tests:
- Mode default is hybrid.
- Mode hybrid runs without error.
- Invalid mode (including legacy) raises.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.app import parse_args
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline


def test_mode_default_is_hybrid():
    with patch.object(sys, "argv", ["app", "dummy_video.mp4"]):
        args = parse_args()
    assert args.mode == "hybrid"


def test_parse_args_accepts_mode_hybrid():
    with patch.object(sys, "argv", ["app", "video.mp4", "--mode", "hybrid"]):
        args = parse_args()
    assert args.mode == "hybrid"


def test_mode_hybrid_runs_without_error():
    pipeline = HybridInventoryPipeline()
    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.gemini_api_key = "test-key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    mock_settings.llm_provider = "gemini"
    dummy_frames = [np.zeros((50, 50, 3), dtype=np.uint8)] * 2
    from src.llm.types import LLMResponse

    mock_executor = MagicMock()
    mock_executor.execute.return_value = LLMResponse(
        provider="gemini", model=None, latency_ms=0,
        parsed_json={"total_entities_detected": 0, "entities": []}, raw_text=None, usage=None,
    )
    with (
        patch("src.frames.sources.video_source.extract_representative_frames") as mock_extract,
        patch(
            "src.pipeline.adapters.gemini_analysis_provider.resolve_llm_executor_for_context",
            return_value=(mock_executor, "gemini"),
        ),
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": [0, 15]})
        with tempfile.TemporaryDirectory() as tmp:
            result = pipeline.process_video(
                "video.mp4",
                mode="hybrid",
                settings=mock_settings,
                video_id="vid",
                output_path=Path(tmp),
                run_id="run1",
                logger=mock_logger,
                args=MagicMock(),
            )
    assert result.exit_code == 0


def test_mode_hybrid_logs_global_analysis():
    pipeline = HybridInventoryPipeline()
    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.gemini_api_key = "key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    mock_settings.llm_provider = "gemini"
    from src.llm.types import LLMResponse

    mock_executor = MagicMock()
    mock_executor.execute.return_value = LLMResponse(
        provider="gemini", model=None, latency_ms=0,
        parsed_json={"total_entities_detected": 0, "entities": []}, raw_text=None, usage=None,
    )
    with (
        patch("src.frames.sources.video_source.extract_representative_frames") as mock_extract,
        patch(
            "src.pipeline.adapters.gemini_analysis_provider.resolve_llm_executor_for_context",
            return_value=(mock_executor, "gemini"),
        ),
    ):
        mock_extract.return_value = ([np.zeros((50, 50, 3), dtype=np.uint8)], {"fps": 30.0, "frame_indices": [0]})
        with tempfile.TemporaryDirectory() as tmp:
            pipeline.process_video(
                "video.mp4",
                mode="hybrid",
                settings=mock_settings,
                video_id="vid",
                output_path=Path(tmp),
                run_id="run1",
                logger=mock_logger,
                args=MagicMock(),
            )
    # Pipeline logs entity count after LLM response
    assert any(
        "Entidades detectadas" in str(c) or "Frames loaded" in str(c)
        for c in mock_logger.info.call_args_list
    )


def test_invalid_mode_raises():
    pipeline = HybridInventoryPipeline()
    mock_logger = MagicMock()
    with pytest.raises(ValueError, match="Invalid mode"):
        pipeline.process_video(
            "video.mp4",
            mode="invalid",
            settings=MagicMock(),
            video_id="vid",
            output_path=Path("/tmp"),
            run_id="run1",
            logger=mock_logger,
            args=MagicMock(),
        )


def test_legacy_mode_raises():
    """Legacy mode has been removed; pipeline raises ValueError."""
    pipeline = HybridInventoryPipeline()
    mock_logger = MagicMock()
    with pytest.raises(ValueError, match="only 'hybrid' is supported"):
        pipeline.process_video(
            "video.mp4",
            mode="legacy",
            settings=MagicMock(),
            video_id="vid",
            output_path=Path("/tmp"),
            run_id="run1",
            logger=mock_logger,
            args=MagicMock(),
        )
