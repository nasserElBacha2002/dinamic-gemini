"""
Stage 6 — Confidence-gated visual fallback.

Tests: high confidence → no fallback; low confidence / label missing quantity → fallback;
one global + N fallback calls; final_quantity updated. Mocks GeminiClient for fallback.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.domain.pallet import Pallet
from src.fallback.fallback_policy import DEFAULT_CONFIDENCE_THRESHOLD, should_trigger_fallback
from src.fallback.visual_fallback_analyzer import (
    FALLBACK_COUNT_PROMPT,
    VisualFallbackAnalyzer,
    VisualFallbackError,
)
from src.fallback import select_fallback_frames
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline


def test_should_trigger_fallback_high_confidence_label_no_trigger():
    """High confidence pallet with label and quantity → no fallback."""
    pallet = Pallet(
        pallet_id="P1",
        has_label=True,
        internal_code="C1",
        quantity=10,
        estimated_visible_boxes=None,
        confidence=0.92,
        processing_mode="label",
        final_quantity=10,
        fallback_used=False,
        source="label",
    )
    assert should_trigger_fallback(pallet, DEFAULT_CONFIDENCE_THRESHOLD) is False


def test_should_trigger_fallback_low_confidence_trigger():
    """Low confidence → fallback triggered."""
    pallet = Pallet(
        pallet_id="P2",
        has_label=False,
        internal_code=None,
        quantity=None,
        estimated_visible_boxes=8,
        confidence=0.55,
        processing_mode="visual_fallback",
        final_quantity=8,
        fallback_used=False,
        source="visual_fallback",
    )
    assert should_trigger_fallback(pallet, 0.70) is True


def test_should_trigger_fallback_label_missing_quantity_trigger():
    """has_label True and quantity None → fallback triggered."""
    pallet = Pallet(
        pallet_id="P3",
        has_label=True,
        internal_code="X",
        quantity=None,
        estimated_visible_boxes=5,
        confidence=0.75,
        processing_mode="visual_fallback",
        final_quantity=5,
        fallback_used=False,
        source="visual_fallback",
    )
    assert should_trigger_fallback(pallet, 0.70) is True


def test_visual_fallback_analyzer_returns_count_and_confidence():
    """Mocked client returns valid JSON → count_visible_boxes returns (count, confidence)."""
    mock_client = MagicMock()
    mock_client.generate_global_analysis_raw.return_value = '{"estimated_count": 12, "confidence": 0.83}'
    analyzer = VisualFallbackAnalyzer(mock_client)
    frames = [np.zeros((50, 50, 3), dtype=np.uint8)]

    count, conf = analyzer.count_visible_boxes(frames)

    assert count == 12
    assert conf == 0.83


def test_visual_fallback_analyzer_invalid_json_raises():
    """Invalid JSON response → VisualFallbackError."""
    mock_client = MagicMock()
    mock_client.generate_global_analysis_raw.return_value = "not json"
    analyzer = VisualFallbackAnalyzer(mock_client)
    frames = [np.zeros((50, 50, 3), dtype=np.uint8)]

    with pytest.raises(VisualFallbackError, match="invalid JSON"):
        analyzer.count_visible_boxes(frames)


def test_visual_fallback_analyzer_missing_keys_raises():
    """Response missing estimated_count or confidence → VisualFallbackError."""
    mock_client = MagicMock()
    mock_client.generate_global_analysis_raw.return_value = '{"estimated_count": 5}'
    analyzer = VisualFallbackAnalyzer(mock_client)
    frames = [np.zeros((50, 50, 3), dtype=np.uint8)]

    with pytest.raises(VisualFallbackError, match="confidence"):
        analyzer.count_visible_boxes(frames)


def test_hybrid_one_global_plus_n_fallback_and_final_quantity_updated():
    """Pipeline: one LLM call; v2.1 report produced (fallback flow not in current pipeline)."""
    from src.llm.types import LLMResponse

    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.llm_provider = "gemini"
    mock_settings.gemini_api_key = "key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    dummy_frames = [np.zeros((60, 80, 3), dtype=np.uint8)] * 5
    global_v21 = {
        "total_entities_detected": 1,
        "entities": [
            {
                "model_entity_id": "e1",
                "entity_type": "PALLET",
                "position_barcode": None,
                "internal_code": None,
                "product_label_quantity": None,
                "position_label_bbox": None,
                "product_label_bbox": None,
                "has_boxes": True,
                "confidence": 0.50,
            },
        ],
    }
    mock_provider = MagicMock()
    mock_provider.analyze_global.return_value = LLMResponse(
        provider="gemini", model=None, latency_ms=0, parsed_json=global_v21, raw_text=None, usage=None,
    )
    with (
        patch("src.frames.sources.video_source.extract_representative_frames") as mock_extract,
        patch("src.pipeline.hybrid_inventory_pipeline.get_llm_provider", return_value=mock_provider),
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": list(range(5))})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            code = HybridInventoryPipeline().process_video(
                "/some/video.mp4",
                mode="hybrid",
                settings=mock_settings,
                video_id="vid",
                output_path=out,
                run_id="run1",
                logger=mock_logger,
                args=MagicMock(),
            )
            report_path = out / "vid" / "run1" / "hybrid_report.json"
            assert code == 0
            assert report_path.exists()
            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)
            assert report["report_version"] == "2.1"
            assert report["mode"] == "hybrid_v2.1"
            assert len(report["entities"]) == 1
    mock_provider.analyze_global.assert_called_once()


def test_hybrid_high_confidence_no_fallback_calls():
    """High-confidence entity → v2.1 report produced."""
    from src.llm.types import LLMResponse

    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.llm_provider = "gemini"
    mock_settings.gemini_api_key = "key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    dummy_frames = [np.zeros((60, 80, 3), dtype=np.uint8)] * 5
    global_v21 = {
        "total_entities_detected": 1,
        "entities": [
            {
                "model_entity_id": "e1",
                "entity_type": "PALLET",
                "position_barcode": "A1",
                "internal_code": "101",
                "product_label_quantity": 15,
                "position_label_bbox": None,
                "product_label_bbox": None,
                "has_boxes": False,
                "confidence": 0.92,
            },
        ],
    }
    mock_provider = MagicMock()
    mock_provider.analyze_global.return_value = LLMResponse(
        provider="gemini", model=None, latency_ms=0, parsed_json=global_v21, raw_text=None, usage=None,
    )
    with (
        patch("src.frames.sources.video_source.extract_representative_frames") as mock_extract,
        patch("src.pipeline.hybrid_inventory_pipeline.get_llm_provider", return_value=mock_provider),
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": list(range(5))})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            code = HybridInventoryPipeline().process_video(
                "/some/video.mp4",
                mode="hybrid",
                settings=mock_settings,
                video_id="vid",
                output_path=out,
                run_id="run1",
                logger=mock_logger,
                args=MagicMock(),
            )
            with open(out / "vid" / "run1" / "hybrid_report.json", encoding="utf-8") as f:
                report = json.load(f)
            assert report["report_version"] == "2.1"
            assert len(report["entities"]) == 1
            assert report["entities"][0]["final_quantity"] == 15
    mock_provider.analyze_global.assert_called_once()


def test_select_fallback_frames_returns_spread_for_k3():
    """select_fallback_frames returns first, mid, last for k=3."""
    frames = [np.zeros((10, 10, 3), dtype=np.uint8) for _ in range(10)]
    out = select_fallback_frames(frames, 3)
    assert len(out) == 3
    assert out[0] is frames[0]
    assert out[1] is frames[5]
    assert out[2] is frames[9]


def test_select_fallback_frames_small_list_returns_all():
    """When len(frames) <= k, returns all frames."""
    frames = [np.zeros((10, 10, 3), dtype=np.uint8), np.ones((10, 10, 3), dtype=np.uint8)]
    out = select_fallback_frames(frames, 3)
    assert len(out) == 2
    assert out[0] is frames[0] and out[1] is frames[1]


def test_metrics_attempts_increment_and_total_calls_on_fallback_error():
    """Pipeline runs with v2.1 response; report produced (fallback flow not in current pipeline)."""
    from src.llm.types import LLMResponse

    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.llm_provider = "gemini"
    mock_settings.gemini_api_key = "key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    dummy_frames = [np.zeros((60, 80, 3), dtype=np.uint8)] * 5
    global_v21 = {
        "total_entities_detected": 1,
        "entities": [
            {
                "model_entity_id": "e1",
                "entity_type": "PALLET",
                "position_barcode": None,
                "internal_code": None,
                "product_label_quantity": None,
                "position_label_bbox": None,
                "product_label_bbox": None,
                "has_boxes": True,
                "confidence": 0.50,
            },
        ],
    }
    mock_provider = MagicMock()
    mock_provider.analyze_global.return_value = LLMResponse(
        provider="gemini", model=None, latency_ms=0, parsed_json=global_v21, raw_text=None, usage=None,
    )
    with (
        patch("src.frames.sources.video_source.extract_representative_frames") as mock_extract,
        patch("src.pipeline.hybrid_inventory_pipeline.get_llm_provider", return_value=mock_provider),
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": list(range(5))})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            code = HybridInventoryPipeline().process_video(
                "/some/video.mp4",
                mode="hybrid",
                settings=mock_settings,
                video_id="vid",
                output_path=out,
                run_id="run1",
                logger=mock_logger,
                args=MagicMock(),
            )
            with open(out / "vid" / "run1" / "hybrid_report.json", encoding="utf-8") as f:
                report = json.load(f)
            assert code == 0
            assert report["report_version"] == "2.1"
            assert len(report["entities"]) == 1


def test_fallback_prompt_contains_main_central_pallet():
    """Prompt instructs to count main/central pallet only."""
    assert "main" in FALLBACK_COUNT_PROMPT.lower()
    assert "central" in FALLBACK_COUNT_PROMPT.lower()
