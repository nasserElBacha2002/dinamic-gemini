"""
Stage 4 — Operational integration.

Tests: processing mode assignment, report structure, low-confidence flags, 0-pallets.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.decision.processing_mode import assign_processing_mode
from src.domain.pallet import Pallet
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline, HYBRID_MAX_FRAMES
from src.reporting.artifacts import write_csv, write_json
from src.reporting.hybrid_report import build_hybrid_report_legacy


def test_assign_processing_mode_label_when_has_label_and_code_and_quantity():
    """Pallet with has_label, internal_code, quantity → source=label, final_quantity=quantity."""
    pallet = Pallet(
        pallet_id="P1",
        has_label=True,
        internal_code="10145317",
        quantity=15,
        estimated_visible_boxes=None,
        confidence=0.92,
    )
    out = assign_processing_mode(pallet)
    assert out.source == "label"
    assert out.processing_mode == "label"
    assert out.final_quantity == 15
    assert out.fallback_used is False


def test_assign_processing_mode_visual_fallback_when_no_label():
    """Pallet without usable label → source=visual_fallback, final_quantity=estimated_visible_boxes."""
    pallet = Pallet(
        pallet_id="P2",
        has_label=False,
        internal_code=None,
        quantity=None,
        estimated_visible_boxes=12,
        confidence=0.78,
    )
    out = assign_processing_mode(pallet)
    assert out.source == "visual_fallback"
    assert out.processing_mode == "visual_fallback"
    assert out.final_quantity == 12
    assert out.fallback_used is False


def test_assign_processing_mode_visual_fallback_when_label_but_missing_quantity():
    """has_label true but quantity None → visual_fallback, final_quantity from estimated_visible_boxes."""
    pallet = Pallet(
        pallet_id="P3",
        has_label=True,
        internal_code="X",
        quantity=None,
        estimated_visible_boxes=8,
        confidence=0.6,
    )
    out = assign_processing_mode(pallet)
    assert out.source == "visual_fallback"
    assert out.final_quantity == 8


def test_build_hybrid_report_structure_and_total_count():
    """Report has correct keys and total_pallets_detected matches len(pallets)."""
    pallets = [
        Pallet("P1", True, "C1", 10, None, 0.9, "label", 10, False, "label"),
        Pallet("P2", False, None, None, 5, 0.7, "visual_fallback", 5, False, "visual_fallback"),
    ]
    report = build_hybrid_report_legacy("/path/to/video.mp4", pallets, frames_selected=20)
    assert report["mode"] == "hybrid"
    assert report["video"]["path"] == "/path/to/video.mp4"
    assert report["video"]["name"] == "video.mp4"
    assert report["frames_selected"] == 20
    assert report["total_pallets_detected"] == 2
    assert len(report["pallets"]) == 2
    assert report["pallets"][0]["pallet_id"] == "P1"
    assert report["pallets"][0]["final_quantity"] == 10
    assert report["pallets"][0]["source"] == "label"
    assert report["pallets"][1]["source"] == "visual_fallback"
    assert report["pallets"][1]["final_quantity"] == 5


def test_build_hybrid_report_low_confidence_flags():
    """Pallets with confidence < threshold appear in flags.low_confidence_pallets."""
    pallets = [
        Pallet("P1", False, None, None, 3, 0.6, "visual_fallback", 3, False, "visual_fallback"),
        Pallet("P2", False, None, None, 2, 0.4, "visual_fallback", 2, False, "visual_fallback"),
    ]
    report = build_hybrid_report_legacy("/v.mp4", pallets, frames_selected=10)
    assert report["flags"]["low_confidence_pallets"] == ["P2"]
    assert report["flags"].get("no_pallets_detected") is not True


def test_build_hybrid_report_zero_pallets_sets_no_pallets_detected():
    """Empty pallets list produces report with flags.no_pallets_detected=true."""
    report = build_hybrid_report_legacy("/v.mp4", [], frames_selected=25)
    assert report["total_pallets_detected"] == 0
    assert report["pallets"] == []
    assert report["flags"]["no_pallets_detected"] is True
    assert report["flags"]["low_confidence_pallets"] == []


def test_write_json_and_write_csv_roundtrip(tmp_path):
    """write_json and write_csv produce files; CSV has expected columns."""
    write_json(tmp_path / "out.json", {"a": 1, "b": [2, 3]})
    with open(tmp_path / "out.json", encoding="utf-8") as f:
        assert json.load(f) == {"a": 1, "b": [2, 3]}

    pallets = [
        Pallet("P1", True, "C1", 10, None, 0.9, "label", 10, False, "label"),
    ]
    csv_path = tmp_path / "out.csv"
    write_csv(csv_path, pallets)
    content = csv_path.read_text(encoding="utf-8")
    assert "pallet_id" in content
    assert "internal_code" in content
    assert "final_quantity" in content
    assert "source" in content
    assert "confidence" in content
    assert "fallback_used" in content
    assert "P1" in content and "label" in content


def test_hybrid_pipeline_writes_hybrid_report_json_and_csv():
    """Full hybrid run writes hybrid_report.json and hybrid_report.csv to run dir."""
    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.gemini_api_key = "key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    dummy_frames = [np.zeros((50, 50, 3), dtype=np.uint8)] * 2
    sample_data = {
        "total_pallets_detected": 1,
        "pallets": [
            {
                "pallet_id": "P1",
                "has_label": True,
                "internal_code": "101",
                "quantity": 5,
                "estimated_visible_boxes": None,
                "confidence": 0.95,
            },
        ],
    }
    with (
        patch("src.pipeline.hybrid_inventory_pipeline.extract_representative_frames") as mock_extract,
        patch("src.pipeline.hybrid_inventory_pipeline.GeminiClient"),
        patch("src.pipeline.hybrid_inventory_pipeline.GeminiGlobalAnalyzer") as mock_analyzer_cls,
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": [0, 15]})
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_video_frames.return_value = sample_data
        mock_analyzer_cls.return_value = mock_analyzer
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
            run_dir = out / "vid" / "run1"
            report_file = run_dir / "hybrid_report.json"
            csv_file = run_dir / "hybrid_report.csv"
            assert code == 0
            assert report_file.exists()
            assert csv_file.exists()
            assert (run_dir / "hybrid_debug.json").exists()
            assert not (run_dir / "hybrid_result.json").exists()
            with open(report_file, encoding="utf-8") as f:
                report = json.load(f)
            assert report["mode"] == "hybrid"
            assert report["total_pallets_detected"] == 1
            assert report["pallets"][0]["source"] == "label"
            assert report["pallets"][0]["final_quantity"] == 5
            assert report["video"]["name"] == "video.mp4"
            assert report["frames_selected"] == 2
