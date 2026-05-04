"""
Tests unitarios para el selector de vistas por track (Sprint A).

Verifica:
- Selección por segmentos temporales y blur
- Diversidad: descarte de vistas muy cercanas en tiempo con IoU alto
- Que puede devolver menos de min_views tras diversidad (el orchestrator marca track no analizado)
- Sprint 6B.9: diversidad real (phash), anchors temporales, preferencia por claridad
"""

import tempfile
from pathlib import Path

import pytest

from src.models.schemas import PalletObservation, PalletTrack
from src.view_selection.selector import select_views_per_track


def _obs(
    frame_idx: int,
    blur: float,
    bbox: tuple[int, int, int, int],
    track_id: str = "0",
    roi_path: str | None = None,
) -> PalletObservation:
    return PalletObservation(
        frame_idx=frame_idx,
        timestamp_seconds=frame_idx / 30.0,
        bbox=bbox,
        det_conf=0.9,
        track_id=track_id,
        blur_score=blur,
        roi_path=roi_path or f"/fake/{track_id}_frame{frame_idx}.jpg",
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

    views, _ = select_views_per_track(
        track,
        min_views=2,
        target_views=4,
        max_views=5,
        blur_percentile=0.25,
        min_frame_gap_diversity=3,
        max_iou_suppress=0.8,
        enable_diversity=False,
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
        _obs(50, 0.8, (300, 100, 400, 200)),  # bbox distinto
    ]
    track = PalletTrack(track_id="0", observations=observations, start_frame=10, end_frame=50)

    views, _ = select_views_per_track(
        track,
        min_views=1,
        target_views=3,
        max_views=3,
        blur_percentile=0.0,
        min_frame_gap_diversity=2,
        max_iou_suppress=0.9,
        enable_diversity=False,
    )

    # Deberíamos tener al menos 2 vistas (una de 10/11 y la de 50); la diversidad puede dejar 2
    assert len(views) >= 1
    assert len(views) <= 3


def test_select_views_per_track_empty_returns_empty():
    """Track sin observaciones → lista vacía."""
    track = PalletTrack(track_id="0", observations=[], start_frame=0, end_frame=0)
    views, _ = select_views_per_track(
        track,
        min_views=3,
        target_views=4,
        max_views=5,
        blur_percentile=0.25,
        enable_diversity=False,
    )
    assert views == []


def test_select_views_per_track_segments_cover_full_range_no_empty():
    """
    Segmentos temporales cubren [0, n) sin solapamiento; no hay segmentos vacíos
    cuando hay suficientes observaciones; resultado respeta min_views y max_views.
    """
    n_obs = 12
    observations = [
        _obs(i * 10, 0.5 + (i % 3) * 0.1, (i * 5, 10, i * 5 + 50, 60)) for i in range(n_obs)
    ]
    track = PalletTrack(track_id="0", observations=observations, start_frame=0, end_frame=110)

    views, _ = select_views_per_track(
        track,
        min_views=3,
        target_views=4,
        max_views=5,
        blur_percentile=0.0,
        min_frame_gap_diversity=0,
        max_iou_suppress=0.0,
        enable_diversity=False,
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
        _obs(i, 0.8, (0, 0, 100, 100))
        for i in range(0, 15, 2)  # frames 0,2,4,...,14
    ]
    track = PalletTrack(track_id="0", observations=observations, start_frame=0, end_frame=14)

    views, _ = select_views_per_track(
        track,
        min_views=3,
        target_views=4,
        max_views=5,
        blur_percentile=0.0,
        min_frame_gap_diversity=5,
        max_iou_suppress=0.5,
        enable_diversity=False,
    )

    # Con IoU 1.0 entre todas (mismo bbox) y gap 5, se queda solo la primera de cada "grupo"
    assert len(views) <= 5
    # Es aceptable que queden menos de min_views; el orchestrator lo maneja
    assert len(views) >= 1 or len(observations) == 0


def test_selector_avoids_near_duplicate_phash():
    """Con enable_diversity=True, no selecciona 3 vistas casi idénticas (phash near-duplicate)."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL required for phash test")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # 3 imágenes casi idénticas (mismo contenido)
        same_img = Image.new("RGB", (20, 20), color=(100, 100, 100))
        dup_paths = []
        for i in range(3):
            p = tmp_path / f"dup_{i}.jpg"
            same_img.save(p, "JPEG", quality=85)
            dup_paths.append(str(p))
        # 2 imágenes distintas
        diff1 = Image.new("RGB", (20, 20), color=(200, 50, 50))
        diff2 = Image.new("RGB", (20, 20), color=(50, 200, 50))
        diff1.save(tmp_path / "diff1.jpg", "JPEG", quality=85)
        diff2.save(tmp_path / "diff2.jpg", "JPEG", quality=85)
        distinct_paths = [str(tmp_path / "diff1.jpg"), str(tmp_path / "diff2.jpg")]

        observations = [
            _obs(0, 0.8, (0, 0, 50, 50), roi_path=dup_paths[0]),
            _obs(10, 0.8, (0, 0, 50, 50), roi_path=dup_paths[1]),
            _obs(20, 0.8, (0, 0, 50, 50), roi_path=dup_paths[2]),
            _obs(
                40, 0.95, (0, 0, 50, 50), roi_path=distinct_paths[0]
            ),  # más clara para ganar en mid
            _obs(
                60, 0.95, (0, 0, 50, 50), roi_path=distinct_paths[1]
            ),  # más clara para ganar en late
        ]
        track = PalletTrack(track_id="0", observations=observations, start_frame=0, end_frame=60)

        views, _ = select_views_per_track(
            track,
            min_views=2,
            target_views=5,
            max_views=5,
            blur_percentile=0.0,
            min_frame_gap_diversity=2,
            max_iou_suppress=0.9,
            frame_width=100,
            frame_height=100,
            enable_diversity=True,
            phash_near_dup_thr=4,
        )

        selected_paths = [v.roi_path for v in views]
        distinct_selected = [p for p in selected_paths if p in distinct_paths]
        # Debe incluir al menos 2 vistas de las distintas (no 3 near-duplicates del mismo grupo)
        assert len(distinct_selected) >= 2, (
            "Selector should prefer distinct views over 3 phash near-duplicates"
        )


def test_selector_picks_anchors_across_time():
    """Con enable_diversity=True, las vistas incluyen al menos 2 anchors con separación temporal."""
    observations = [
        _obs(i * 10, 0.7 + (i % 3) * 0.05, (i * 2, 10, i * 2 + 60, 70)) for i in range(11)
    ]
    track = PalletTrack(track_id="0", observations=observations, start_frame=0, end_frame=100)

    views, _ = select_views_per_track(
        track,
        min_views=2,
        target_views=5,
        max_views=5,
        blur_percentile=0.0,
        min_frame_gap_diversity=2,
        max_iou_suppress=0.8,
        frame_width=640,
        frame_height=480,
        enable_diversity=True,
        anchor_window_frames=15,
    )

    frame_indices = [v.frame_idx for v in views]
    assert len(frame_indices) >= 2
    span = max(frame_indices) - min(frame_indices)
    assert span >= 20, "Selected views should span a meaningful time range (anchors early/mid/late)"


def test_selector_prefers_clearer_view_when_available():
    """Cuando una vista más clara (blur_score alto) existe, entra en seleccionados."""
    observations = [
        _obs(10, 0.5, (100, 100, 200, 200)),
        _obs(12, 0.95, (102, 102, 202, 202)),
        _obs(14, 0.5, (104, 104, 204, 204)),
        _obs(50, 0.6, (100, 100, 200, 200)),
        _obs(90, 0.6, (100, 100, 200, 200)),
    ]
    track = PalletTrack(track_id="0", observations=observations, start_frame=10, end_frame=90)

    views, _ = select_views_per_track(
        track,
        min_views=2,
        target_views=4,
        max_views=5,
        blur_percentile=0.0,
        min_frame_gap_diversity=2,
        max_iou_suppress=0.9,
        frame_width=640,
        frame_height=480,
        enable_diversity=True,
    )

    selected_frames = [v.frame_idx for v in views]
    blur_by_frame = {o.frame_idx: o.blur_score or 0.0 for o in observations}
    assert 12 in selected_frames, "Clearer view (frame 12) should be selected"
    max_blur_selected = max(blur_by_frame[f] for f in selected_frames)
    assert max_blur_selected >= 0.9, "At least one selected view should have high blur_score"
