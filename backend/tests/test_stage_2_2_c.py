"""Stage 2.2.C — Photo normalization & cost optimization.

Tests: resize/no-resize, manifest update, PhotosFrameSource prefers normalized,
pipeline uses normalized paths for photos jobs.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.frames.normalize import (
    decode_image_bytes,
    encode_jpeg,
    normalize_image,
    normalize_photo_file,
    normalize_photos_for_job,
    photos_use_normalized,
    validate_relative_path,
)
from src.frames.sources.photos_source import PhotosFrameSource
from src.jobs.models import JobInput


def _small_image(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_normalization_resizes_large_image(tmp_path):
    """Normalize reduces a large image so longest side <= max_side."""
    img = _small_image(2000, 1500)
    src = tmp_path / "big.jpg"
    cv2.imwrite(str(src), img)
    dst = tmp_path / "normalized.jpg"

    metrics = normalize_photo_file(
        src, dst,
        max_side=1280,
        jpeg_quality=85,
        min_side=320,
    )

    assert metrics["original_w"] == 2000
    assert metrics["original_h"] == 1500
    assert metrics["resized"] is True
    assert metrics["normalized_w"] <= 1280
    assert metrics["normalized_h"] <= 1280
    assert max(metrics["normalized_w"], metrics["normalized_h"]) == 1280
    assert dst.is_file()
    decoded = cv2.imread(str(dst))
    assert decoded.shape[1] == metrics["normalized_w"]
    assert decoded.shape[0] == metrics["normalized_h"]


def test_normalization_keeps_small_image_dimensions(tmp_path):
    """Normalize does not upscale; small image keeps dimensions."""
    img = _small_image(400, 300)
    src = tmp_path / "small.jpg"
    cv2.imwrite(str(src), img)
    dst = tmp_path / "normalized.jpg"

    metrics = normalize_photo_file(
        src, dst,
        max_side=1280,
        jpeg_quality=85,
        min_side=64,
    )

    assert metrics["original_w"] == 400
    assert metrics["original_h"] == 300
    assert metrics["resized"] is False
    assert metrics["normalized_w"] == 400
    assert metrics["normalized_h"] == 300
    assert dst.is_file()


def test_normalization_rejects_too_small_image(tmp_path):
    """Image with a side below min_side raises ValueError."""
    img = _small_image(200, 150)
    src = tmp_path / "tiny.jpg"
    cv2.imwrite(str(src), img)
    dst = tmp_path / "normalized.jpg"

    with pytest.raises(ValueError, match="below minimum side"):
        normalize_photo_file(
            src, dst,
            max_side=1280,
            jpeg_quality=85,
            min_side=320,
        )


def test_decode_image_bytes_valid():
    img = _small_image(10, 10)
    _, buf = cv2.imencode(".jpg", img)
    raw = buf.tobytes()
    out = decode_image_bytes(raw)
    assert out.shape == (10, 10, 3)


def test_decode_image_bytes_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        decode_image_bytes(b"")


def test_encode_jpeg_returns_bytes():
    img = _small_image(100, 100)
    out = encode_jpeg(img, 85)
    assert isinstance(out, bytes)
    assert len(out) > 0


def test_normalize_image_no_resize():
    img = _small_image(800, 600)
    out = normalize_image(img, max_side=1280, min_side=64)
    assert out.shape == img.shape


def test_normalize_image_resizes():
    img = _small_image(1600, 1200)
    out = normalize_image(img, max_side=1280, min_side=64)
    assert out.shape != img.shape
    assert max(out.shape[1], out.shape[0]) == 1280


def test_manifest_updated_with_metrics_and_normalized_paths(tmp_path):
    """normalize_photos_for_job updates manifest with metrics and stored_normalized_filename."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    img = _small_image(400, 400)  # both sides >= min_side 320
    cv2.imwrite(str(photos_dir / "0001_a.jpg"), img)
    cv2.imwrite(str(photos_dir / "0002_b.jpg"), _small_image(400, 400))
    manifest = {
        "input_type": "photos",
        "total_photos": 2,
        "total_bytes_original": 0,
        "photos": [
            {"index": 1, "original_filename": "a.jpg", "stored_filename": "0001_a.jpg", "bytes": 100},
            {"index": 2, "original_filename": "b.jpg", "stored_filename": "0002_b.jpg", "bytes": 100},
        ],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    settings = MagicMock()
    settings.photo_resize_max_side = 1280
    settings.photo_jpeg_quality = 85
    settings.photos_min_side = 320

    normalize_photos_for_job(run_dir, settings)

    with open(run_dir / "input_manifest.json", encoding="utf-8") as f:
        updated = json.load(f)
    assert "total_bytes_normalized" in updated
    assert "normalization" in updated
    assert updated["normalization"]["resize_max_side"] == 1280
    assert updated["normalization"]["jpeg_quality"] == 85
    for entry in updated["photos"]:
        assert "stored_normalized_filename" in entry
        assert "normalized_bytes" in entry
        assert "normalized_w" in entry
        assert "normalized_h" in entry
        assert "resized" in entry
    norm_dir = run_dir / "input_photos_normalized"
    assert norm_dir.is_dir()
    assert (norm_dir / updated["photos"][0]["stored_normalized_filename"]).is_file()
    assert (norm_dir / updated["photos"][1]["stored_normalized_filename"]).is_file()


def test_photos_source_prefers_normalized_when_present(tmp_path):
    """When manifest has stored_normalized_filename and normalized dir exists, PhotosFrameSource returns normalized paths."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    norm_dir = run_dir / "input_photos_normalized"
    norm_dir.mkdir()
    img = _small_image(64, 64)
    cv2.imwrite(str(photos_dir / "0001_a.jpg"), img)
    cv2.imwrite(str(norm_dir / "0001_a.jpg"), img)  # normalized version
    manifest = {
        "input_type": "photos",
        "total_photos": 1,
        "photos": [
            {
                "index": 1,
                "stored_filename": "0001_a.jpg",
                "stored_normalized_filename": "0001_a.jpg",
                "normalized_bytes": 500,
                "normalized_w": 64,
                "normalized_h": 64,
                "resized": False,
            },
        ],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    job_input = JobInput(video_path="", input_type="photos")
    source = PhotosFrameSource()
    bundle = source.get_frames("job_1", run_dir, job_input)

    assert len(bundle.frames) == 1
    assert "input_photos_normalized" in str(bundle.frames[0])
    assert bundle.frames[0].parent == norm_dir


def test_photos_source_uses_originals_when_normalized_missing(tmp_path):
    """When normalized dir or files are missing, PhotosFrameSource falls back to originals."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    img = _small_image(64, 64)
    cv2.imwrite(str(photos_dir / "0001_a.jpg"), img)
    manifest = {
        "input_type": "photos",
        "total_photos": 1,
        "photos": [{"index": 1, "stored_filename": "0001_a.jpg"}],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    job_input = JobInput(video_path="", input_type="photos")
    source = PhotosFrameSource()
    bundle = source.get_frames("job_1", run_dir, job_input)

    assert len(bundle.frames) == 1
    assert bundle.frames[0].parent == photos_dir
    assert bundle.frames[0].name == "0001_a.jpg"


def test_validate_relative_path_accepts_safe():
    assert validate_relative_path("run/input_manifest.json", "x") == "run/input_manifest.json"
    assert validate_relative_path("  custom/photos  ", "x") == "custom/photos"


def test_validate_relative_path_rejects_unsafe():
    with pytest.raises(ValueError, match="must not contain"):
        validate_relative_path("run/../etc/passwd", "x")
    with pytest.raises(ValueError, match="relative path"):
        validate_relative_path("/absolute/path", "x")
    with pytest.raises(ValueError, match="backslashes"):
        validate_relative_path("run\\input_photos", "x")


def test_normalize_photo_file_respects_max_single_bytes(tmp_path):
    """When max_single_bytes is set and file exceeds it, raises ValueError."""
    img = _small_image(100, 100)
    src = tmp_path / "big.jpg"
    cv2.imwrite(str(src), img)
    raw_len = src.stat().st_size
    dst = tmp_path / "out.jpg"
    with pytest.raises(ValueError, match="exceeds limit"):
        normalize_photo_file(src, dst, max_side=1280, jpeg_quality=85, max_single_bytes=raw_len - 1)
    normalize_photo_file(src, dst, max_side=1280, jpeg_quality=85, max_single_bytes=raw_len + 1)
    assert dst.is_file()


def test_normalize_photos_for_job_skips_when_normalized_and_snapshot_matches(tmp_path):
    """When photos_use_normalized and normalization snapshot matches settings, return without rewriting."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    norm_dir = run_dir / "input_photos_normalized"
    norm_dir.mkdir()
    img = _small_image(400, 400)
    cv2.imwrite(str(photos_dir / "0001_a.jpg"), img)
    cv2.imwrite(str(norm_dir / "0001_a.jpg"), img)
    manifest = {
        "input_type": "photos",
        "total_photos": 1,
        "photos": [
            {
                "index": 1,
                "stored_filename": "0001_a.jpg",
                "stored_normalized_filename": "0001_a.jpg",
                "normalized_bytes": 100,
                "normalized_w": 400,
                "normalized_h": 400,
                "resized": False,
            },
        ],
        "normalization": {"resize_max_side": 1280, "jpeg_quality": 85, "min_side": 320},
    }
    manifest_path = run_dir / "input_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    settings = MagicMock()
    settings.photo_resize_max_side = 1280
    settings.photo_jpeg_quality = 85
    settings.photos_min_side = 320

    normalize_photos_for_job(run_dir, settings)

    # Manifest content unchanged (fast-path skipped rewrite)
    after = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert after["normalization"] == {"resize_max_side": 1280, "jpeg_quality": 85, "min_side": 320}
    assert after["photos"][0]["stored_normalized_filename"] == "0001_a.jpg"


def test_write_manifest_atomic_uses_temp_then_replace(tmp_path):
    """Atomic write: content appears in target path only after replace; no partial file."""
    from src.frames.normalize import _write_manifest_atomic

    target = tmp_path / "input_manifest.json"
    target.write_text('{"old": true}', encoding="utf-8")
    new_manifest = {"input_type": "photos", "total_photos": 0, "photos": []}
    _write_manifest_atomic(target, new_manifest)
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == new_manifest
    assert "old" not in data
    # No leftover temp file
    temps = list(tmp_path.glob("input_manifest.*.json"))
    assert len(temps) == 0


def test_photos_source_raises_on_unsafe_manifest_path():
    """PhotosFrameSource rejects unsafe input_manifest_path."""
    from src.frames.sources.photos_source import PhotosFrameSource

    run_dir = Path("/tmp/run")
    job_input = JobInput(video_path="", input_type="photos", input_manifest_path="../../../etc/passwd")
    source = PhotosFrameSource()
    with pytest.raises(ValueError, match="must not contain"):
        source.get_frames("j", run_dir, job_input)


def test_photos_for_job_raises_filenotfound_for_missing_photo(tmp_path):
    """normalize_photos_for_job raises FileNotFoundError (not ValueError) for missing photo file."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    # Do not create 0001_a.jpg
    manifest = {
        "input_type": "photos",
        "total_photos": 1,
        "photos": [{"index": 1, "stored_filename": "0001_a.jpg"}],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = MagicMock()
    settings.photo_resize_max_side = 1280
    settings.photo_jpeg_quality = 85
    settings.photos_min_side = 64
    with pytest.raises(FileNotFoundError, match="photo file not found"):
        normalize_photos_for_job(run_dir, settings)


def test_photos_use_normalized_false_when_no_normalized_dir(tmp_path):
    manifest = {"input_type": "photos", "photos": [{"stored_normalized_filename": "0001_a.jpg"}]}
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert photos_use_normalized(run_dir, manifest) is False


def test_photos_use_normalized_false_when_entry_missing_field(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "input_photos_normalized").mkdir()
    manifest = {"input_type": "photos", "photos": [{"stored_filename": "0001_a.jpg"}]}
    assert photos_use_normalized(run_dir, manifest) is False


def test_integration_photos_job_pipeline_uses_normalized_paths(tmp_path):
    """Photos job: pipeline runs normalization then get_frames returns normalized paths; bundle paths are under input_photos_normalized."""
    run_dir = tmp_path / "job_photos" / "run"
    run_dir.mkdir(parents=True)
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    manifest = {
        "input_type": "photos",
        "total_photos": 2,
        "total_bytes_original": 0,
        "photos": [
            {"index": 1, "stored_filename": "0001_p1.jpg", "bytes": 1000},
            {"index": 2, "stored_filename": "0002_p2.jpg", "bytes": 1000},
        ],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    img = _small_image(400, 400)  # both sides >= min_side 320
    cv2.imwrite(str(photos_dir / "0001_p1.jpg"), img)
    cv2.imwrite(str(photos_dir / "0002_p2.jpg"), img)

    settings = MagicMock()
    settings.photo_resize_max_side = 1280
    settings.photo_jpeg_quality = 85
    settings.photos_min_side = 320

    normalize_photos_for_job(run_dir, settings)

    job_input = JobInput(video_path="", input_type="photos")
    source = PhotosFrameSource()
    bundle = source.get_frames("job_photos", run_dir, job_input)

    assert len(bundle.frames) == 2
    for p in bundle.frames:
        assert "input_photos_normalized" in str(p)
        assert p.exists()

    # Run pipeline _run_hybrid with mock provider and confirm it loads from bundle (normalized)
    from src.llm.types import LLMResponse
    from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

    v21_response = {"total_entities_detected": 0, "entities": []}
    logger = MagicMock()
    settings.llm_provider = "gemini"
    settings.gemini_api_key = "test-key"
    settings.gemini_model_name = "gemini-2.0-flash-exp"
    settings.gemini_max_retries = 1
    settings.gemini_retry_delay = 0.1
    settings.debug_save_frames = False
    settings.hybrid_max_frames = None

    mock_provider = MagicMock()
    mock_provider.analyze_global.return_value = LLMResponse(
        provider="gemini", model=None, latency_ms=0, parsed_json=v21_response, raw_text=None, usage=None,
    )
    with patch("src.pipeline.hybrid_inventory_pipeline.get_llm_provider", return_value=mock_provider):
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
    # Pipeline loads from bundle (normalized paths) and passes them to the provider
    call_args = mock_provider.analyze_global.call_args
    request = call_args[0][0]
    assert len(request.frames) == 2
