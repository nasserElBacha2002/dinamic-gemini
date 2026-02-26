"""
Tests unitarios para el pipeline track-based (Sprint A).

Verifica:
- Early return cuando hay 0 tracks: resultado vacío y summary con pipeline_debug
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.models.schemas import FrameRef
from src.pipeline.orchestrator import run_pipeline


@pytest.fixture
def mock_settings():
    """Settings mínimos para el pipeline (stub, sin synthetic)."""
    settings = MagicMock()
    settings.use_synthetic_detection = False
    settings.detector_mode = "stub"
    settings.detection_conf_threshold = 0.5
    settings.tracker_min_hits = 3
    settings.tracker_max_age = 30
    settings.roi_padding_pct = 0.12
    settings.roi_max_side = 1280
    settings.roi_jpeg_quality = 85
    settings.min_views = 3
    settings.target_views = 4
    settings.max_views = 5
    settings.view_selection_blur_percentile = 0.25
    settings.view_selection_min_frame_gap_diversity = 3
    settings.view_selection_max_iou_suppress = 0.8
    settings.gemini_api_key = "test-key"
    settings.gemini_model_name = "gemini-2.0-flash-exp"
    settings.gemini_max_retries = 1
    settings.gemini_retry_delay = 0.1
    return settings


def test_run_pipeline_zero_tracks_returns_empty_results_and_summary(mock_settings):
    """
    Con detector stub (0 detecciones) el pipeline hace early return:
    track_results=[], summary con frames_extracted, tracks_detected=0, pipeline_debug.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = Path(tmpdir) / "fake.mp4"
        video_path.write_bytes(b"fake")  # archivo existente pero no video válido
        output_dir = str(tmpdir)
        run_id = "test_run_001"
        video_id = "test_video"

        with (
            patch("src.pipeline.orchestrator.load_video_metadata", return_value=MagicMock(fps=30.0)),
            patch(
                "src.pipeline.orchestrator.extract_frames",
                return_value=[
                    FrameRef(frame_idx=0, timestamp_seconds=0.0, width=100, height=100),
                    FrameRef(frame_idx=30, timestamp_seconds=1.0, width=100, height=100),
                ],
            ),
            patch("src.pipeline.orchestrator.cv2.VideoCapture") as mock_cap,
            patch("src.pipeline.orchestrator.read_frame_at", return_value=np.zeros((100, 100, 3), dtype=np.uint8)),
            patch("src.pipeline.orchestrator.detect_pallets_per_frame", return_value=[]),
        ):
            mock_cap.return_value.isOpened.return_value = True
            mock_cap.return_value.release = MagicMock()

            track_results, summary = run_pipeline(
                str(video_path),
                video_id=video_id,
                settings=mock_settings,
                output_dir=output_dir,
                run_id=run_id,
                extract_fps=1.0,
                prompt_profile="multi_view_per_track",
                save_debug_frames=False,
                save_annotated_views=False,
            )

        assert track_results == []
        assert summary["frames_extracted"] == 2
        assert summary["tracks_detected"] == 0
        assert summary["tracks_analyzed"] == 0
        assert "pipeline_debug" in summary
        debug = summary["pipeline_debug"]
        assert debug["frame_count"] == 2
        assert debug["detector_mode"] == "stub"
        assert debug["detections_per_frame"] == [0, 0]
