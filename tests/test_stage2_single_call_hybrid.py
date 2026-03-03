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
from src.parsing.global_analysis_parser import GlobalAnalysisParseError, parse_global_analysis
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline, HYBRID_MAX_FRAMES
from src.video.frames import extract_representative_frames


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


def test_hybrid_mode_calls_gemini_analyzer_once():
    pipeline = HybridInventoryPipeline()
    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.gemini_api_key = "test-key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    dummy_frames = [np.zeros((100, 100, 3), dtype=np.uint8)] * 3
    with (
        patch("src.pipeline.hybrid_inventory_pipeline.extract_representative_frames") as mock_extract,
        patch("src.pipeline.hybrid_inventory_pipeline.GeminiGlobalAnalyzer") as mock_analyzer_cls,
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": [0, 10, 20]})
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_video_frames.return_value = SAMPLE_GLOBAL_RESPONSE
        mock_analyzer_cls.return_value = mock_analyzer
        with tempfile.TemporaryDirectory() as tmp:
            code = pipeline.process_video(
                "video.mp4",
                mode="hybrid",
                settings=mock_settings,
                video_id="vid",
                output_path=Path(tmp),
                run_id="run1",
                logger=mock_logger,
                args=MagicMock(),
            )
    assert code == 0
    mock_analyzer.analyze_video_frames.assert_called_once()
    call_frames = mock_analyzer.analyze_video_frames.call_args[0][0]
    assert len(call_frames) == 3


def test_hybrid_run_returns_success_and_writes_result():
    pipeline = HybridInventoryPipeline()
    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.gemini_api_key = "key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    dummy_frames = [np.zeros((50, 50, 3), dtype=np.uint8)] * 2
    with (
        patch("src.pipeline.hybrid_inventory_pipeline.extract_representative_frames") as mock_extract,
        patch("src.pipeline.hybrid_inventory_pipeline.GeminiClient") as mock_client_cls,
        patch("src.pipeline.hybrid_inventory_pipeline.GeminiGlobalAnalyzer") as mock_analyzer_cls,
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": [0, 15]})
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_video_frames.return_value = SAMPLE_GLOBAL_RESPONSE
        mock_analyzer_cls.return_value = mock_analyzer
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            code = pipeline.process_video(
                "video.mp4",
                mode="hybrid",
                settings=mock_settings,
                video_id="vid",
                output_path=out,
                run_id="run1",
                logger=mock_logger,
                args=MagicMock(),
            )
            result_file = out / "vid" / "run1" / "hybrid_debug.json"
            assert code == 0
            assert result_file.exists()
            with open(result_file, encoding="utf-8") as f:
                report = json.load(f)
            assert report["mode"] == "hybrid"
            assert report["total_pallets_detected"] == 2
            assert len(report["pallets"]) == 2
            assert report["pallets"][0]["pallet_id"] == "P1"
            assert report["pallets"][0]["quantity"] == 15


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


def test_gemini_global_analyzer_parses_json_with_prefix_and_suffix():
    """Analyzer extracts and parses JSON when Gemini returns text before and after the JSON."""
    raw_response = (
        "Here is the analysis you requested:\n"
        '{"total_pallets_detected": 0, "pallets": []}\n'
        "End of response."
    )
    mock_client = MagicMock()
    mock_client.generate_global_analysis_raw.return_value = raw_response
    analyzer = GeminiGlobalAnalyzer(mock_client)
    one_frame = [np.zeros((50, 50, 3), dtype=np.uint8)]

    result = analyzer.analyze_video_frames(one_frame)

    assert result == {"total_pallets_detected": 0, "pallets": []}
