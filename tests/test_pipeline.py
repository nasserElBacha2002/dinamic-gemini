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
    settings.reid_enabled = False
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


def test_run_pipeline_reid_disabled_does_not_call_reid(mock_settings):
    """Con reid_enabled=False el pipeline no invoca run_reid_pipeline."""
    mock_settings.reid_enabled = False
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = Path(tmpdir) / "fake.mp4"
        video_path.write_bytes(b"fake")
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
            patch("src.pipeline.orchestrator.run_reid_pipeline") as mock_reid,
        ):
            mock_cap.return_value.isOpened.return_value = True
            mock_cap.return_value.release = MagicMock()

            run_pipeline(
                str(video_path),
                video_id="vid",
                settings=mock_settings,
                output_dir=str(tmpdir),
                run_id="run1",
                extract_fps=1.0,
            )
            mock_reid.assert_not_called()


def test_run_pipeline_reid_enabled_calls_passthrough_and_summary_has_metrics(mock_settings):
    """Con reid_enabled=True se llama run_reid_pipeline y summary incluye métricas Re-ID."""
    from src.models.schemas import PalletObservation, PalletTrack

    mock_settings.reid_enabled = True
    mock_settings.use_synthetic_detection = True
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = Path(tmpdir) / "fake.mp4"
        video_path.write_bytes(b"fake")
        roi_dir = Path(tmpdir) / "vid" / "run1" / "rois"
        roi_dir.mkdir(parents=True)
        (roi_dir / "0_frame0.jpg").write_bytes(b"x")
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
            patch("src.pipeline.orchestrator.run_reid_pipeline") as mock_reid,
            patch("src.pipeline.orchestrator.GeminiClient") as mock_gemini_cls,
        ):
            mock_cap.return_value.isOpened.return_value = True
            mock_cap.return_value.release = MagicMock()
            obs = [
                PalletObservation(
                    frame_idx=0,
                    timestamp_seconds=0.0,
                    bbox=(10, 10, 50, 50),
                    det_conf=0.9,
                    track_id="0",
                    blur_score=0.8,
                    roi_path=str(roi_dir / "0_frame0.jpg"),
                )
            ]
            stub_track = PalletTrack(track_id="0", observations=obs, start_frame=0, end_frame=0)
            mock_reid.return_value = ([stub_track], {
                "tracks_before_reid": 1,
                "tracks_after_reid": 1,
                "tracks_merged_count": 0,
                "reid_candidates_generated": 0,
                "reid_pairs_after_phash": 0,
                "reid_pairs_confirmed": 0,
                "clip_verifications_run": 0,
            })
            mock_gemini_cls.return_value.analyze_track.return_value = None

            track_results, summary = run_pipeline(
                str(video_path),
                video_id="vid",
                settings=mock_settings,
                output_dir=str(tmpdir),
                run_id="run1",
                extract_fps=1.0,
            )

            mock_reid.assert_called_once()
            pd = summary.get("pipeline_debug") or {}
            assert pd.get("tracks_before_reid") == 1
            assert pd.get("tracks_after_reid") == 1
            assert pd.get("tracks_merged_count") == 0
            assert summary.get("tracks_before_reid") == 1
            assert summary.get("tracks_after_reid") == 1
            assert summary.get("reid_pairs_after_phash") == 0
            assert summary.get("reid_pairs_confirmed") == 0
            assert summary["requests_sent"] == pd.get("tracks_requests_sent"), "requests_sent debe coincidir con tracks_requests_sent"


def test_run_pipeline_reid_full_flow_no_merges(mock_settings):
    """Con reid_enabled=True se ejecuta el flujo Re-ID real (sin mock); CLIP stub => sin merges."""
    mock_settings.reid_enabled = True
    mock_settings.use_synthetic_detection = True
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = Path(tmpdir) / "fake.mp4"
        video_path.write_bytes(b"fake")
        roi_dir = Path(tmpdir) / "vid" / "run1" / "rois"
        roi_dir.mkdir(parents=True)
        (roi_dir / "0_frame0.jpg").write_bytes(b"x")
        (roi_dir / "1_frame0.jpg").write_bytes(b"y")
        metadata = MagicMock(fps=30.0, width=100, height=100)
        with (
            patch("src.pipeline.orchestrator.load_video_metadata", return_value=metadata),
            patch(
                "src.pipeline.orchestrator.extract_frames",
                return_value=[
                    FrameRef(frame_idx=0, timestamp_seconds=0.0, width=100, height=100),
                    FrameRef(frame_idx=30, timestamp_seconds=1.0, width=100, height=100),
                ],
            ),
            patch("src.pipeline.orchestrator.cv2.VideoCapture") as mock_cap,
            patch("src.pipeline.orchestrator.read_frame_at", return_value=np.zeros((100, 100, 3), dtype=np.uint8)),
            patch("src.pipeline.orchestrator.GeminiClient") as mock_gemini_cls,
        ):
            mock_cap.return_value.isOpened.return_value = True
            mock_cap.return_value.release = MagicMock()
            mock_gemini_cls.return_value.analyze_track.return_value = None

            track_results, summary = run_pipeline(
                str(video_path),
                video_id="vid",
                settings=mock_settings,
                output_dir=str(tmpdir),
                run_id="run1",
                extract_fps=1.0,
            )

            pd = summary.get("pipeline_debug") or {}
            assert summary.get("tracks_before_reid") == summary.get("tracks_after_reid")
            assert summary.get("reid_pairs_confirmed") == 0
            assert summary.get("tracks_merged_count") == 0
            assert pd.get("reid_pairs_after_phash") is not None
            assert pd.get("reid_pairs_confirmed") == 0
            assert "reid_merge_map" in pd


def test_make_summary_requests_sent_equals_tracks_requests_sent():
    """summary['requests_sent'] refleja el valor explícito pasado (tracks_requests_sent)."""
    from src.pipeline.orchestrator import _make_summary

    summary = _make_summary(
        100,
        5,
        5,
        20,
        4,
        start_time=0.0,
        requests_sent=3,
    )
    assert summary["requests_sent"] == 3
