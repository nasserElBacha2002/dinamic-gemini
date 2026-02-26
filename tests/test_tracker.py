"""
Tests unitarios para el tracker multi-objeto (Sprint A).

Verifica:
- update() con detecciones por frame
- get_tracks() devuelve historial frame_idx -> [(bbox, track_id)]
- Asociación por IoU entre frames
"""

import pytest

from src.models.schemas import BBox
from src.tracking.tracker import MultiObjectTracker, TrackedBBox


def test_tracker_update_two_frames_same_bbox_assigns_same_track_id():
    """Dos frames con una detección en posición similar → mismo track_id."""
    tracker = MultiObjectTracker(min_hits=1, max_age=5, iou_threshold=0.3)
    # bbox (x1, y1, x2, y2, conf)
    bbox1: BBox = (10.0, 20.0, 100.0, 120.0, 0.9)
    bbox2: BBox = (12.0, 22.0, 102.0, 122.0, 0.9)  # desplazamiento pequeño → IoU alto

    out1 = tracker.update([bbox1], frame_idx=0)
    out2 = tracker.update([bbox2], frame_idx=1)

    assert len(out1) == 1
    assert len(out2) == 1
    _, tid1 = out1[0]
    _, tid2 = out2[0]
    assert tid1 == tid2

    tracks = tracker.get_tracks()
    assert 0 in tracks and 1 in tracks
    assert len(tracks[0]) == 1 and len(tracks[1]) == 1
    assert tracks[0][0][1] == tid1
    assert tracks[1][0][1] == tid2


def test_tracker_update_two_frames_different_bboxes_assigns_different_track_ids():
    """Dos frames con bboxes sin solapamiento → dos track_ids distintos."""
    tracker = MultiObjectTracker(min_hits=1, max_age=5, iou_threshold=0.3)
    left: BBox = (10.0, 10.0, 50.0, 80.0, 0.9)
    right: BBox = (200.0, 10.0, 240.0, 80.0, 0.9)

    out1 = tracker.update([left], frame_idx=0)
    out2 = tracker.update([right], frame_idx=1)

    assert len(out1) == 1 and len(out2) == 1
    _, tid1 = out1[0]
    _, tid2 = out2[0]
    assert tid1 != tid2

    tracks = tracker.get_tracks()
    assert len(tracks) == 2
    assert tracks[0][0][1] == tid1
    assert tracks[1][0][1] == tid2


def test_tracker_get_tracks_returns_copy_of_history():
    """get_tracks() devuelve dict con frame_idx y lista de (bbox, track_id)."""
    tracker = MultiObjectTracker(min_hits=1, max_age=10)
    bbox: BBox = (0.0, 0.0, 10.0, 10.0, 0.95)
    tracker.update([bbox], frame_idx=0)

    tracks = tracker.get_tracks()
    assert isinstance(tracks, dict)
    assert 0 in tracks
    assert len(tracks[0]) == 1
    b, tid = tracks[0][0]
    assert b == bbox
    assert isinstance(tid, str)
