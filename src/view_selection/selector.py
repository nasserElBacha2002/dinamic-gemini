"""
Selector de vistas por track (Sprint A).

Elige 3-5 vistas por PalletTrack: filtro por blur, segmentos temporales,
mejor vista por segmento (blur_score + área ROI).
"""

from typing import List

import numpy as np

from src.models.schemas import PalletObservation, PalletTrack


def _bbox_area(bbox: tuple[int, int, int, int]) -> int:
    """Área del bbox (x1, y1, x2, y2)."""
    return max(0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


def _bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """IoU entre dos bboxes (x1, y1, x2, y2)."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    aa = _bbox_area(a)
    ab = _bbox_area(b)
    union = aa + ab - inter
    return inter / union if union > 0 else 0.0


def select_views_per_track(
    track: PalletTrack,
    min_views: int,
    target_views: int,
    max_views: int,
    blur_percentile: float = 0.25,
    min_frame_gap_diversity: int = 3,
    max_iou_suppress: float = 0.8,
) -> List[PalletObservation]:
    """Selecciona las mejores vistas por track para enviar a Gemini.

    Algoritmo:
    1. Filtrar observaciones con blur_score < percentil 25 del track.
    2. Ordenar por frame_idx.
    3. Dividir el track en K=target_views segmentos temporales.
    4. En cada segmento elegir la observación con mayor blur_score (y mayor área como desempate).
    5. Diversidad: descartar vistas demasiado cercanas en tiempo y con bbox muy similar (IoU alto).

    Args:
        track: PalletTrack con observaciones (blur_score y roi_path opcionales).
        min_views: Mínimo de vistas a devolver (si hay menos, se devuelven todas las que haya).
        target_views: Número objetivo de vistas.
        max_views: Máximo de vistas a devolver.
        blur_percentile: Percentil por debajo del cual se descartan observaciones (0 a 1).
        min_frame_gap_diversity: Mínimo salto en frame_idx para considerar vista distinta (evita duplicados).
        max_iou_suppress: Si dos vistas están a <= min_frame_gap frames y sus bboxes tienen IoU > este valor, se queda una. 0 = desactivado.

    Returns:
        Lista de hasta max_views PalletObservation (entre min_views y max_views si hay suficientes).
        Nota: Tras el paso de diversidad puede quedar len(selected) < min_views; en ese caso el
        orchestrator considera el track no analizado (no envía a Gemini y devuelve (track_id, None)).
    """
    if not track.observations:
        return []

    # Blur score: None -> 0 para ordenar/filtrar
    scores = [o.blur_score if o.blur_score is not None else 0.0 for o in track.observations]
    threshold = float(
        np.quantile(scores, blur_percentile) if len(scores) > 1 else scores[0]
    )
    filtered = [o for o in track.observations if (o.blur_score or 0.0) >= threshold]
    if not filtered:
        filtered = track.observations

    filtered.sort(key=lambda o: o.frame_idx)
    k = min(target_views, max_views, len(filtered))
    if k <= 0:
        return filtered[:max_views] if len(filtered) >= min_views else filtered

    # Segmentos temporales: k segmentos que cubren [0, n) sin solapamiento
    n = len(filtered)
    if k >= n:
        return filtered[:max_views]

    step = n / k
    selected: List[PalletObservation] = []
    for seg in range(k):
        j_start = int(seg * step)
        j_end = int((seg + 1) * step)
        if j_end > n:
            j_end = n
        segment = filtered[j_start:j_end]
        if not segment:
            continue
        best = max(
            segment,
            key=lambda o: (
                o.blur_score if o.blur_score is not None else 0.0,
                _bbox_area(o.bbox),
            ),
        )
        selected.append(best)

    # Respetar min_views: si nos quedamos cortos, rellenar con las mejores restantes
    if len(selected) < min_views and len(filtered) >= min_views:
        remaining = [o for o in filtered if o not in selected]
        remaining.sort(
            key=lambda o: (o.blur_score or 0.0, _bbox_area(o.bbox)),
            reverse=True,
        )
        for o in remaining:
            if len(selected) >= min_views:
                break
            selected.append(o)
        selected.sort(key=lambda o: o.frame_idx)

    # Diversidad: no enviar dos vistas muy cercanas en tiempo y con bbox casi igual (IoU alto)
    if max_iou_suppress > 0 and min_frame_gap_diversity >= 0 and len(selected) > 1:
        selected.sort(key=lambda o: o.frame_idx)
        kept: List[PalletObservation] = []
        for cand in selected:
            too_similar = False
            for k in kept:
                if abs(cand.frame_idx - k.frame_idx) <= min_frame_gap_diversity and _bbox_iou(
                    cand.bbox, k.bbox
                ) > max_iou_suppress:
                    too_similar = True
                    break
            if not too_similar:
                kept.append(cand)
        selected = kept

    return selected[:max_views]
