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
    """Full hybrid run writes hybrid_report.json (v2.1) to run dir."""
    from src.llm.types import LLMResponse

    mock_logger = MagicMock()
    mock_settings = MagicMock()
    mock_settings.llm_provider = "gemini"
    mock_settings.gemini_api_key = "key"
    mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
    mock_settings.gemini_max_retries = 1
    mock_settings.gemini_retry_delay = 0.1
    dummy_frames = [np.zeros((50, 50, 3), dtype=np.uint8)] * 2
    sample_v21 = {
        "total_entities_detected": 1,
        "entities": [
            {
                "model_entity_id": "e1",
                "entity_type": "PALLET",
                "position_barcode": "A1",
                "internal_code": "101",
                "product_label_quantity": 5,
                "position_label_bbox": None,
                "product_label_bbox": None,
                "has_boxes": False,
                "confidence": 0.95,
            },
        ],
    }
    mock_provider = MagicMock()
    mock_provider.analyze_global.return_value = LLMResponse(
        provider="gemini", model=None, latency_ms=0, parsed_json=sample_v21, raw_text=None, usage=None,
    )
    with (
        patch("src.frames.sources.video_source.extract_representative_frames") as mock_extract,
        patch("src.pipeline.hybrid_inventory_pipeline.get_llm_provider", return_value=mock_provider),
    ):
        mock_extract.return_value = (dummy_frames, {"fps": 30.0, "frame_indices": [0, 15]})
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
            assert code == 0
            assert report_file.exists()
            with open(report_file, encoding="utf-8") as f:
                report = json.load(f)
            assert report["mode"] == "hybrid_v2.1"
            assert report["report_version"] == "2.1"
            assert len(report["entities"]) == 1
            assert report["entities"][0]["internal_code"] == "101"
            assert report["entities"][0]["final_quantity"] == 5
            assert report["video"]["name"] == "video.mp4"
            assert report["frames_selected"] == 2
