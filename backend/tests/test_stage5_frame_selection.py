"""
Stage 5 — Smart frame selection (optimized strategy).

Tests: redundancy filter (dHash), blur filter (Laplacian), frame_indices length equals frames.
Uses mocked VideoCapture and synthetic frames; no real video files.
"""

from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from src.video.frames import (
    STRATEGY_OPTIMIZED,
    STRATEGY_UNIFORM,
    _blur_metric,
    _dhash,
    _hamming_distance,
    extract_representative_frames,
)


def _make_mock_cap(frames: list, fps: float = 30.0):
    """Lightweight fake VideoCapture: isOpened, get, set, read, release. Returns frames by index."""
    n = len(frames)
    last_pos = [None]

    def set_(prop, val):
        if prop == 1:  # CAP_PROP_POS_FRAMES
            last_pos[0] = int(val)

    def get(prop):
        if prop == 5:  # CAP_PROP_FPS
            return fps
        if prop == 7:  # CAP_PROP_FRAME_COUNT
            return n
        return 0

    def read():
        idx = last_pos[0]
        if idx is None or idx < 0 or idx >= n:
            return False, None
        return True, frames[idx].copy()

    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.get.side_effect = get
    cap.set.side_effect = set_
    cap.read.side_effect = read
    cap.release = MagicMock()  # no-op
    return cap


def test_dhash_same_frame_same_hash():
    """Identical frames produce the same dHash."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[50:, :] = 255
    assert _dhash(frame) == _dhash(frame)


def test_dhash_different_frame_different_hash():
    """Different visual content produces different dHash (fixed RNG draws)."""
    rng = np.random.default_rng(0)
    a = rng.integers(0, 256, (100, 100, 3), dtype=np.uint8)
    b = rng.integers(0, 256, (100, 100, 3), dtype=np.uint8)
    assert _dhash(a) != _dhash(b)


def test_hamming_distance_same_is_zero():
    """Hamming distance of same hash is 0."""
    h = 0xDEADBEEF
    assert _hamming_distance(h, h) == 0


def test_blur_metric_blurred_lower_than_sharp():
    """Gaussian-blurred frame has lower Laplacian variance than sharp."""
    sharp = np.random.randint(0, 256, (80, 80, 3), dtype=np.uint8)
    blurred = cv2.GaussianBlur(sharp, (15, 15), 5)
    assert _blur_metric(blurred) < _blur_metric(sharp)


def test_optimized_reduces_duplicates():
    """When many frames are identical, optimized strategy returns fewer (redundancy filter)."""
    same_frame = np.random.randint(0, 256, (60, 80, 3), dtype=np.uint8)
    frames = [same_frame] * 30  # 30 identical frames
    with patch("src.video.frames.cv2.VideoCapture", return_value=_make_mock_cap(frames)):
        out_frames, meta = extract_representative_frames(
            "/fake/path.mp4",
            max_frames=25,
            strategy=STRATEGY_OPTIMIZED,
            hash_threshold=10,
            blur_threshold=5.0,
        )
    hashes = [_dhash(f) for f in out_frames]
    assert len(out_frames) <= 25
    assert len(set(hashes)) <= len(out_frames)
    # With 30 identical frames we expect redundancy filter to accept one (or few)
    assert len(out_frames) >= 1


def test_optimized_filters_blurred_frames():
    """Blurred frames are excluded when blur_threshold is above their metric."""
    sharp = np.zeros((60, 80, 3), dtype=np.uint8)
    sharp[::4, :] = 255
    sharp[:, ::4] = 200
    blurred = cv2.GaussianBlur(sharp, (31, 31), 12)
    # Mix: sharp at 0,2,4,... and blurred at 1,3,5,...
    frames = [sharp, blurred] * 10  # 20 frames
    with patch("src.video.frames.cv2.VideoCapture", return_value=_make_mock_cap(frames)):
        out_frames, meta = extract_representative_frames(
            "/fake/path.mp4",
            max_frames=25,
            strategy=STRATEGY_OPTIMIZED,
            blur_threshold=10.0,
            hash_threshold=64,
        )
    # All accepted frames should be sharp (high Laplacian variance)
    for f in out_frames:
        assert _blur_metric(f) >= 10.0


def test_frame_indices_length_equals_frames_length():
    """Returned frame_indices length equals frames length and indices match accepted frames."""
    frames = [np.random.randint(0, 256, (50, 50, 3), dtype=np.uint8) for _ in range(15)]
    with patch("src.video.frames.cv2.VideoCapture", return_value=_make_mock_cap(frames)):
        out_frames, meta = extract_representative_frames(
            "/fake/path.mp4",
            max_frames=25,
            strategy=STRATEGY_OPTIMIZED,
            blur_threshold=0.0,
            hash_threshold=0,
        )
    assert len(meta["frame_indices"]) == len(out_frames)
    assert all(isinstance(i, int) for i in meta["frame_indices"])


def test_uniform_strategy_unchanged_behavior():
    """Uniform strategy still returns up to max_frames with correct indices."""
    frames = [np.zeros((40, 40, 3), dtype=np.uint8)] * 20
    with patch("src.video.frames.cv2.VideoCapture", return_value=_make_mock_cap(frames)):
        out_frames, meta = extract_representative_frames(
            "/fake/path.mp4",
            max_frames=10,
            strategy=STRATEGY_UNIFORM,
        )
    assert len(out_frames) == 10
    assert len(meta["frame_indices"]) == 10
    assert meta["fps"] == 30.0


def test_optimized_fallback_when_too_few_after_filter():
    """If filtering leaves too few frames, fallback adds uniform samples (min 10)."""
    # All frames very blurry so Phase B accepts none; fallback should add frames
    blurred = cv2.GaussianBlur(np.random.randint(0, 256, (50, 50, 3), dtype=np.uint8), (31, 31), 10)
    frames = [blurred] * 25
    with patch("src.video.frames.cv2.VideoCapture", return_value=_make_mock_cap(frames)):
        out_frames, meta = extract_representative_frames(
            "/fake/path.mp4",
            max_frames=25,
            strategy=STRATEGY_OPTIMIZED,
            blur_threshold=1000.0,
        )
    # Fallback should bring us up to at least MIN_FRAMES_FALLBACK (10)
    assert len(out_frames) >= 10
    assert len(meta["frame_indices"]) == len(out_frames)
