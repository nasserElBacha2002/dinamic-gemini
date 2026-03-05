"""
Stage 2.2.B — FrameSource strategy: VideoFrameSource, PhotosFrameSource, factory, pipeline integration.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.frames.types import FramesBundle
from src.frames.sources.factory import get_frame_source
from src.frames.sources.photos_source import PhotosFrameSource
from src.frames.sources.video_source import VideoFrameSource
from src.jobs.models import JobInput


# ---------- Factory ----------


def test_frame_source_factory_video():
    source = get_frame_source("video")
    assert isinstance(source, VideoFrameSource)


def test_frame_source_factory_photos():
    source = get_frame_source("photos")
    assert isinstance(source, PhotosFrameSource)


def test_frame_source_factory_unknown_raises():
    with pytest.raises(ValueError, match="unknown input_type"):
        get_frame_source("unknown")
    with pytest.raises(ValueError, match="unknown input_type"):
        get_frame_source("image")


# ---------- VideoFrameSource ----------


def test_video_frame_source_returns_frames_bundle(tmp_path):
    """VideoFrameSource extracts frames, persists to run_dir/.frames_extract_*, not frames_sent."""
    video_path = tmp_path / "sample.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    w, h = 320, 240
    out = cv2.VideoWriter(str(video_path), fourcc, 10.0, (w, h))
    for _ in range(30):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        out.write(frame)
    out.release()
    assert video_path.exists()

    job_input = JobInput(video_path=str(video_path), mode="hybrid", input_type="video")
    run_dir = tmp_path / "run"
    source = VideoFrameSource()
    with patch("src.frames.sources.video_source.load_settings") as mock_load:
        mock_load.return_value = MagicMock(hybrid_max_frames=10)
        bundle = source.get_frames("job_1", run_dir, job_input)

    assert isinstance(bundle, FramesBundle)
    assert bundle.metadata.get("source") == "video"
    assert bundle.metadata.get("selected_by") == "video_sampling"
    assert bundle.metadata.get("frame_count") == len(bundle.frames)
    assert len(bundle.frames) <= 10
    assert len(bundle.frames) == len(bundle.frame_refs)
    # VideoFrameSource writes to .frames_extract_* only (pipeline writes frames_sent when debug_save_frames)
    assert not (run_dir / "frames_sent").exists()
    extract_dirs = [d for d in run_dir.iterdir() if d.is_dir() and d.name.startswith(".frames_extract_")]
    assert len(extract_dirs) == 1
    for p in bundle.frames:
        assert p.exists()
        assert p.suffix == ".jpg"


def test_video_frame_source_empty_video_path_raises():
    job_input = JobInput(video_path="", mode="hybrid", input_type="video")
    source = VideoFrameSource()
    with pytest.raises(ValueError, match="video_path is required"):
        source.get_frames("job_1", Path("/tmp/run"), job_input)


# ---------- PhotosFrameSource ----------


def test_photos_frame_source_reads_manifest(tmp_path):
    """PhotosFrameSource reads input_manifest.json and returns frames in index order."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    manifest = {
        "input_type": "photos",
        "total_photos": 2,
        "photos": [
            {"index": 1, "stored_filename": "0001_a.jpg"},
            {"index": 2, "stored_filename": "0002_b.jpg"},
        ],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cv2.imwrite(str(photos_dir / "0001_a.jpg"), img)
    cv2.imwrite(str(photos_dir / "0002_b.jpg"), img)

    job_input = JobInput(
        video_path="",
        input_type="photos",
        input_manifest_path="run/input_manifest.json",
        photos_dir="run/input_photos",
    )
    source = PhotosFrameSource()
    bundle = source.get_frames("job_1", run_dir, job_input)

    assert bundle.metadata["source"] == "photos"
    assert bundle.metadata["selected_by"] == "uploaded_photos"
    assert bundle.metadata["frame_count"] == 2
    assert len(bundle.frames) == 2
    assert len(bundle.frame_refs) == 2
    assert "photo_0001" in bundle.frame_refs
    assert "photo_0002" in bundle.frame_refs
    assert bundle.frames[0].name == "0001_a.jpg"
    assert bundle.frames[1].name == "0002_b.jpg"


def test_photos_frame_source_missing_file(tmp_path):
    """PhotosFrameSource raises FileNotFoundError if a manifest-listed file is missing."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    manifest = {
        "input_type": "photos",
        "total_photos": 1,
        "photos": [{"index": 1, "stored_filename": "0001_missing.jpg"}],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    # Do not create 0001_missing.jpg

    job_input = JobInput(video_path="", input_type="photos")
    source = PhotosFrameSource()
    with pytest.raises(FileNotFoundError, match="missing input photo"):
        source.get_frames("job_1", run_dir, job_input)


def test_photos_frame_source_missing_manifest(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    job_input = JobInput(video_path="", input_type="photos")
    source = PhotosFrameSource()
    with pytest.raises(FileNotFoundError, match="manifest not found"):
        source.get_frames("job_1", run_dir, job_input)


def test_photos_frame_source_uses_job_input_manifest_and_photos_dir(tmp_path):
    """When job_input.input_manifest_path and job_input.photos_dir are set, use those paths (relative to job_dir)."""
    job_dir = tmp_path / "job_1"
    run_dir = job_dir / "run"
    run_dir.mkdir(parents=True)
    custom = job_dir / "custom"
    custom.mkdir()
    photos_sub = custom / "photos"
    photos_sub.mkdir()
    manifest = {
        "input_type": "photos",
        "total_photos": 1,
        "photos": [{"index": 1, "stored_filename": "img1.jpg"}],
    }
    (custom / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cv2.imwrite(str(photos_sub / "img1.jpg"), img)

    job_input = JobInput(
        video_path="",
        input_type="photos",
        input_manifest_path="custom/manifest.json",
        photos_dir="custom/photos",
    )
    source = PhotosFrameSource()
    bundle = source.get_frames("job_1", run_dir, job_input)

    assert bundle.metadata["source"] == "photos"
    assert bundle.metadata["frame_count"] == 1
    assert len(bundle.frames) == 1
    assert bundle.frames[0].name == "img1.jpg"
    assert bundle.frames[0].parent == photos_sub


# ---------- Pipeline integration (smoke with photos + mock analyzer) ----------


def test_pipeline_runs_with_photos_frames(tmp_path):
    """Pipeline with photos job: FrameSource returns bundle; mock analyzer returns v2.1 JSON; report written."""
    run_dir = tmp_path / "job_photos" / "run"
    run_dir.mkdir(parents=True)
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    manifest = {
        "input_type": "photos",
        "total_photos": 2,
        "photos": [
            {"index": 1, "stored_filename": "0001_p1.jpg"},
            {"index": 2, "stored_filename": "0002_p2.jpg"},
        ],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    cv2.imwrite(str(photos_dir / "0001_p1.jpg"), img)
    cv2.imwrite(str(photos_dir / "0002_p2.jpg"), img)

    job_input = JobInput(
        video_path="",
        input_type="photos",
        input_manifest_path="run/input_manifest.json",
        photos_dir="run/input_photos",
    )
    v21_response = {
        "total_entities_detected": 1,
        "entities": [
            {
                "model_entity_id": "e1",
                "entity_type": "PALLET",
                "position_barcode": None,
                "internal_code": "C1",
                "product_label_quantity": 2,
                "position_label_bbox": None,
                "product_label_bbox": None,
                "has_boxes": True,
                "confidence": 0.9,
            }
        ],
    }

    from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

    logger = MagicMock()
    settings = MagicMock()
    settings.gemini_api_key = "test-key"
    settings.gemini_model_name = "gemini-2.0-flash-exp"
    settings.gemini_max_retries = 1
    settings.gemini_retry_delay = 0.1
    settings.debug_save_frames = False
    # Stage 2.2.C: normalization runs for photos; set min_side so 64x64 test images pass
    settings.photo_resize_max_side = 1280
    settings.photo_jpeg_quality = 85
    settings.photos_min_side = 64

    with patch("src.pipeline.hybrid_inventory_pipeline.GeminiClient"):
        with patch("src.pipeline.hybrid_inventory_pipeline.GeminiGlobalAnalyzer") as MockAnalyzer:
            MockAnalyzer.return_value.analyze_video_frames.return_value = v21_response
            pipe = HybridInventoryPipeline()
            code = pipe._run_hybrid(
                "",
                settings=settings,
                video_id="job_photos",
                output_path=tmp_path,
                run_id="run",
                logger=logger,
                job_input=job_input,
            )
    assert code == 0
    report_path = run_dir / "hybrid_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report.get("report_version") == "2.1"
    assert report.get("mode") == "hybrid_v2.1"
    assert report.get("frames_selected") == 2
    assert len(report.get("entities", [])) >= 1


def test_pipeline_truncates_frames_to_hybrid_max_frames(tmp_path):
    """Pipeline loads at most hybrid_max_frames (or HYBRID_MAX_FRAMES_LOAD_CAP) into RAM."""
    run_dir = tmp_path / "job_photos" / "run"
    run_dir.mkdir(parents=True)
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    manifest_photos = [{"index": i, "stored_filename": f"p_{i:04d}.jpg"} for i in range(1, 61)]
    manifest = {"input_type": "photos", "total_photos": 60, "photos": manifest_photos}
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    img = np.zeros((32, 32, 3), dtype=np.uint8)
    for i in range(1, 61):
        cv2.imwrite(str(photos_dir / f"p_{i:04d}.jpg"), img)

    job_input = JobInput(video_path="", input_type="photos")
    v21_response = {"total_entities_detected": 0, "entities": []}

    from src.pipeline.hybrid_inventory_pipeline import (
        HYBRID_MAX_FRAMES_LOAD_CAP,
        HybridInventoryPipeline,
    )

    logger = MagicMock()
    settings = MagicMock()
    settings.gemini_api_key = "test-key"
    settings.gemini_model_name = "gemini-2.0-flash-exp"
    settings.gemini_max_retries = 1
    settings.gemini_retry_delay = 0.1
    settings.debug_save_frames = False
    settings.hybrid_max_frames = None
    # Stage 2.2.C: normalization runs for photos; allow 32x32 test images
    settings.photo_resize_max_side = 1280
    settings.photo_jpeg_quality = 85
    settings.photos_min_side = 32

    with patch("src.pipeline.hybrid_inventory_pipeline.GeminiClient"):
        with patch("src.pipeline.hybrid_inventory_pipeline.GeminiGlobalAnalyzer") as MockAnalyzer:
            MockAnalyzer.return_value.analyze_video_frames.return_value = v21_response
            pipe = HybridInventoryPipeline()
            pipe._run_hybrid(
                "",
                settings=settings,
                video_id="job_photos",
                output_path=tmp_path,
                run_id="run",
                logger=logger,
                job_input=job_input,
            )
            call_args = MockAnalyzer.return_value.analyze_video_frames.call_args
            assert call_args is not None
            frames_passed = call_args[0][0]
    assert len(frames_passed) == HYBRID_MAX_FRAMES_LOAD_CAP
