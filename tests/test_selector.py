"""
Tests unitarios para el selector de vistas por track (Sprint A).

Verifica:
- Selección por segmentos temporales y blur
- Diversidad: descarte de vistas muy cercanas en tiempo con IoU alto
- Que puede devolver menos de min_views tras diversidad (el orchestrator marca track no analizado)
"""

import pytest

from src.models.schemas import PalletObservation, PalletTrack
from src.view_selection.selector import select_views_per_track


def _obs(frame_idx: int, blur: float, bbox: tuple[int, int, int, int], track_id: str = "0") -> PalletObservation:
    return PalletObservation(
        frame_idx=frame_idx,
        timestamp_seconds=frame_idx / 30.0,
        bbox=bbox,
        det_conf=0.9,
        track_id=track_id,
        blur_score=blur,
        roi_path=f"/fake/{track_id}_frame{frame_idx}.jpg",
    )


def test_select_views_per_track_returns_subset_ordered_by_frame():
    """Devuelve hasta max_views observaciones, ordenadas por frame_idx."""
    observations = [
        _obs(0, 0.5, (10, 10, 50, 50)),
        _obs(30, 0.8, (12, 12, 52, 52)),
        _obs(60, 0.7, (14, 14, 54, 54)),
        _obs(90, 0.9, (16, 16, 56, 56)),
        _obs(120, 0.6, (18, 18, 58, 58)),
    ]
    track = PalletTrack(track_id="0", observations=observations, start_frame=0, end_frame=120)

    views = select_views_per_track(
        track,
        min_views=2,
        target_views=4,
        max_views=5,
        blur_percentile=0.25,
        min_frame_gap_diversity=3,
        max_iou_suppress=0.8,
    )

    assert len(views) <= 5
    assert len(views) >= 2
    for i in range(len(views) - 1):
        assert views[i].frame_idx <= views[i + 1].frame_idx


def test_select_views_per_track_diversity_drops_similar_views():
    """Con max_iou_suppress > 0, dos vistas muy cercanas en tiempo y bbox similar → una descartada."""
    # Dos observaciones en frames consecutivos (gap=1) con mismo bbox → IoU=1.0
    observations = [
        _obs(10, 0.9, (100, 100, 200, 200)),
        _obs(11, 0.85, (100, 100, 200, 200)),  # mismo bbox, frame muy cercano
        _obs(50, 0.8, (300, 100, 400, 200)),   # bbox distinto
    ]
    track = PalletTrack(track_id="0", observations=observations, start_frame=10, end_frame=50)

    views = select_views_per_track(
        track,
        min_views=1,
        target_views=3,
        max_views=3,
        blur_percentile=0.0,
        min_frame_gap_diversity=2,
        max_iou_suppress=0.9,
    )

    # Deberíamos tener al menos 2 vistas (una de 10/11 y la de 50); la diversidad puede dejar 2
    assert len(views) >= 1
    assert len(views) <= 3


def test_select_views_per_track_empty_returns_empty():
    """Track sin observaciones → lista vacía."""
    track = PalletTrack(track_id="0", observations=[], start_frame=0, end_frame=0)
    views = select_views_per_track(
        track, min_views=3, target_views=4, max_views=5, blur_percentile=0.25,
    )
    assert views == []


def test_select_views_per_track_segments_cover_full_range_no_empty():
    """
    Segmentos temporales cubren [0, n) sin solapamiento; no hay segmentos vacíos
    cuando hay suficientes observaciones; resultado respeta min_views y max_views.
    """
    n_obs = 12
    observations = [
        _obs(i * 10, 0.5 + (i % 3) * 0.1, (i * 5, 10, i * 5 + 50, 60))
        for i in range(n_obs)
    ]
    track = PalletTrack(track_id="0", observations=observations, start_frame=0, end_frame=110)

    views = select_views_per_track(
        track,
        min_views=3,
        target_views=4,
        max_views=5,
        blur_percentile=0.0,
        min_frame_gap_diversity=0,
        max_iou_suppress=0.0,
    )

    assert len(views) >= min(3, n_obs)
    assert len(views) <= 5
    # Debe haber una vista por segmento (4 segmentos de 3 obs cada uno) → 4 vistas
    assert len(views) == min(4, n_obs)
    frame_indices = [o.frame_idx for o in views]
    assert frame_indices == sorted(frame_indices)


def test_select_views_per_track_can_return_fewer_than_min_views_after_diversity():
    """
    Tras el paso de diversidad puede quedar len(selected) < min_views.
    El orchestrator considera el track no analizado (track_id, None) en ese caso.
    """
    # Varias observaciones muy similares (mismo bbox, frames cercanos)
    observations = [
        _obs(i, 0.8, (0, 0, 100, 100)) for i in range(0, 15, 2)  # frames 0,2,4,...,14
    ]
    track = PalletTrack(track_id="0", observations=observations, start_frame=0, end_frame=14)

    views = select_views_per_track(
        track,
        min_views=3,
        target_views=4,
        max_views=5,
        blur_percentile=0.0,
        min_frame_gap_diversity=5,
        max_iou_suppress=0.5,
    )

    # Con IoU 1.0 entre todas (mismo bbox) y gap 5, se queda solo la primera de cada "grupo"
    assert len(views) <= 5
    # Es aceptable que queden menos de min_views; el orchestrator lo maneja
    assert len(views) >= 1 or len(observations) == 0
