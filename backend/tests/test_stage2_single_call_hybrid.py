"""
Stage 2 — Single global Gemini call (hybrid path).

Tests:
- Only one Gemini call in hybrid execution.
- Parser validates sample JSON and produces Pallet objects.
- run_hybrid returns success and writes structured result.
- extract_representative_frames returns correct indices when a frame read fails.
- GeminiGlobalAnalyzer parses JSON when response has text prefix/suffix.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.domain.pallet import Pallet
from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer
from src.llm.types import LLMResponse
from src.parsing.global_analysis_parser import GlobalAnalysisParseError, parse_global_analysis
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline, HYBRID_MAX_FRAMES
from src.video.frames import extract_representative_frames


# v2.1 shape for pipeline (parse_entities); legacy shape for parse_global_analysis tests
SAMPLE_V21_RESPONSE = {
    "total_entities_detected": 2,
    "entities": [
        {
            "model_entity_id": "e1",
            "entity_type": "PALLET",
            "position_barcode": None,
            "internal_code": "10145317",
            "product_label_quantity": 15,
            "position_label_bbox": None,
            "product_label_bbox": None,
            "has_boxes": False,
            "confidence": 0.94,
        },
        {
            "model_entity_id": "e2",
            "entity_type": "PALLET",
            "position_barcode": None,
            "internal_code": None,
            "product_label_quantity": None,
            "position_label_bbox": None,
            "product_label_bbox": None,
            "has_boxes": True,
            "confidence": 0.78,
        },
    ],
}

SAMPLE_GLOBAL_RESPONSE = {
    "total_pallets_detected": 2,
    "pallets": [
        {
            "pallet_id": "P1",
            "has_label": True,
            "internal_code": "10145317",
            "quantity": 15,
            "estimated_visible_boxes": None,
            "confidence": 0.94,
        },
        {
            "pallet_id": "P2",
            "has_label": False,
            "internal_code": None,
            "quantity": None,
            "estimated_visible_boxes": 12,
            "confidence": 0.78,
        },
    ],
}


def test_parse_global_analysis_returns_pallet_objects():
    pallets = parse_global_analysis(SAMPLE_GLOBAL_RESPONSE)
    assert len(pallets) == 2
    assert all(isinstance(p, Pallet) for p in pallets)
    assert pallets[0].pallet_id == "P1"
    assert pallets[0].has_label is True
    assert pallets[0].internal_code == "10145317"
    assert pallets[0].quantity == 15
    assert pallets[0].confidence == 0.94
    assert pallets[1].pallet_id == "P2"
    assert pallets[1].has_label is False
    assert pallets[1].estimated_visible_boxes == 12
    assert pallets[1].confidence == 0.78


def test_parse_global_analysis_total_mismatch_raises():
    bad = {**SAMPLE_GLOBAL_RESPONSE, "total_pallets_detected": 3}
    with pytest.raises(GlobalAnalysisParseError, match="total_pallets_detected.*len"):
        parse_global_analysis(bad)


def test_parse_global_analysis_duplicate_pallet_id_raises():
    bad = {
        "total_pallets_detected": 2,
        "pallets": [
            SAMPLE_GLOBAL_RESPONSE["pallets"][0],
            {**SAMPLE_GLOBAL_RESPONSE["pallets"][1], "pallet_id": "P1"},
        ],
    }
    with pytest.raises(GlobalAnalysisParseError, match="duplicado"):
        parse_global_analysis(bad)


def test_parse_global_analysis_confidence_out_of_range_raises():
    bad = {
        "total_pallets_detected": 1,
        "pallets": [{**SAMPLE_GLOBAL_RESPONSE["pallets"][0], "confidence": 1.5}],
    }
    with pytest.raises(GlobalAnalysisParseError, match="0,1"):
        parse_global_analysis(bad)


def test_hybrid_mode_calls_llm_provider_once():
    """Hybrid path uses registry-resolved executor; execute() called once."""
    pipeline = HybridInventoryPipeline()
    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.llm_provider = "gemini"
    mock_settings.gemini_api_key = "test-key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    dummy_frames = [np.zeros((100, 100, 3), dtype=np.uint8)] * 3
    mock_executor = MagicMock()
    mock_executor.execute.return_value = LLMResponse(
        provider="gemini", model="gemini-2.0-flash-exp", latency_ms=100,
        parsed_json=SAMPLE_V21_RESPONSE, raw_text=None, usage=None,
    )
    with (
        patch("src.frames.sources.video_source.extract_representative_frames") as mock_extract,
        patch(
            "src.pipeline.adapters.hybrid_global_analysis_strategy.resolve_llm_executor_for_context",
            return_value=(mock_executor, "gemini"),
        ),
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": [0, 10, 20]})
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
    mock_executor.execute.assert_called_once()
    call_request = mock_executor.execute.call_args[0][0]
    assert len(call_request.frames) == 3


def test_hybrid_run_returns_success_and_writes_result():
    pipeline = HybridInventoryPipeline()
    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.llm_provider = "gemini"
    mock_settings.gemini_api_key = "key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    dummy_frames = [np.zeros((50, 50, 3), dtype=np.uint8)] * 2
    mock_executor = MagicMock()
    mock_executor.execute.return_value = LLMResponse(
        provider="gemini", model="gemini-2.0-flash-exp", latency_ms=100,
        parsed_json=SAMPLE_V21_RESPONSE, raw_text=None, usage=None,
    )
    with (
        patch("src.frames.sources.video_source.extract_representative_frames") as mock_extract,
        patch(
            "src.pipeline.adapters.hybrid_global_analysis_strategy.resolve_llm_executor_for_context",
            return_value=(mock_executor, "gemini"),
        ),
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": [0, 15]})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run_result = pipeline.process_video(
                "video.mp4",
                mode="hybrid",
                settings=mock_settings,
                video_id="vid",
                output_path=out,
                run_id="run1",
                logger=mock_logger,
                args=MagicMock(),
            )
            result_file = out / "vid" / "run1" / "hybrid_report.json"
            assert run_result.exit_code == 0
            assert result_file.exists()
            with open(result_file, encoding="utf-8") as f:
                report = json.load(f)
            assert report["mode"] == "hybrid_v2.1"
            assert report["report_version"] == "2.1"
            assert len(report["entities"]) == 2
            assert report["entities"][0]["model_entity_id"] == "e1"
            assert report["entities"][0].get("internal_code") == "10145317"


def test_extract_representative_frames_indices_match_when_one_read_fails():
    """When one frame read fails, frame_indices contains only indices of successfully read frames."""
    dummy_frame = np.zeros((60, 80, 3), dtype=np.uint8)
    fail_at_index = 10

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else 100  # FPS=30, FRAME_COUNT=100
    last_pos = [None]

    def track_set(prop, val):
        if prop == 1:  # CAP_PROP_POS_FRAMES
            last_pos[0] = int(val)

    def read():
        if last_pos[0] == fail_at_index:
            return False, None
        return True, dummy_frame.copy()

    mock_cap.set.side_effect = track_set
    mock_cap.read.side_effect = lambda: read()

    with patch("src.video.frames.cv2.VideoCapture", return_value=mock_cap):
        frames, meta = extract_representative_frames("/fake/video.mp4", max_frames=25, strategy="uniform")

    assert len(meta["frame_indices"]) == len(frames)
    assert fail_at_index not in meta["frame_indices"]
    for i, idx in enumerate(meta["frame_indices"]):
        assert isinstance(idx, int)
        assert idx != fail_at_index


def test_gemini_global_analyzer_parses_structured_json():
    """Analyzer returns parsed dict when client returns JSON string (structured output)."""
    json_response = '{"total_entities_detected": 0, "entities": []}'
    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = json_response
    analyzer = GeminiGlobalAnalyzer(mock_client)
    one_frame = [np.zeros((50, 50, 3), dtype=np.uint8)]

    result = analyzer.analyze_video_frames(one_frame)

    assert result == {"total_entities_detected": 0, "entities": []}
