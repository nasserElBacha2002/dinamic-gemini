"""
Selector de vistas por track (Sprint A + 6B.9).

Elige 3-5 vistas por PalletTrack: claridad (blur), área, y diversidad real
(temporal + phash + centroide). Soporta modo legacy (segmentos) y modo
2 fases (anchors + greedy diversidad) cuando enable_diversity=True.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.models.schemas import PalletObservation, PalletTrack

logger = logging.getLogger(__name__)


def _bbox_area(bbox: tuple[int, int, int, int]) -> int:
    """Área del bbox (x1, y1, x2, y2)."""
    return max(0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


def _bbox_center(bbox: tuple[int, int, int, int]) -> Tuple[float, float]:
    """Centro del bbox (cx, cy)."""
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


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


def _phash_for_roi(roi_path: Optional[str], cache: Dict[str, Optional[str]]) -> Optional[str]:
    """Calcula pHash del ROI; cache por path. Retorna None si no hay path o falla."""
    if not roi_path or not roi_path.strip():
        return None
    if roi_path in cache:
        return cache[roi_path]
    try:
        from PIL import Image
        import imagehash
        p = Path(roi_path)
        if not p.exists():
            cache[roi_path] = None
            return None
        with Image.open(p) as img:
            img_rgb = img.convert("RGB").copy()
        h = imagehash.phash(img_rgb)
        cache[roi_path] = str(h)
        return cache[roi_path]
    except Exception as e:
        logger.debug("phash %s: %s", roi_path, e)
        cache[roi_path] = None
        return None


def _phash_dist_hex(h1: Optional[str], h2: Optional[str]) -> int:
    """Distancia Hamming entre dos hashes hex; 64 si alguno es None."""
    if h1 is None or h2 is None:
        return 64
    try:
        import imagehash
        a, b = imagehash.hex_to_hash(h1), imagehash.hex_to_hash(h2)
        return int(a - b)
    except Exception:
        return 64


def _centroid_normalized(
    bbox: tuple[int, int, int, int],
    frame_width: Optional[int],
    frame_height: Optional[int],
) -> Tuple[float, float]:
    """Centroide normalizado (cx, cy) en [0,1]. Si no hay dimensiones válidas, usa fallback."""
    cx, cy = _bbox_center(bbox)
    if (
        frame_width is not None
        and frame_height is not None
        and isinstance(frame_width, (int, float))
        and isinstance(frame_height, (int, float))
        and frame_width > 0
        and frame_height > 0
    ):
        return (cx / frame_width, cy / frame_height)
    return (min(1.0, cx / max(1, bbox[2] - bbox[0])), min(1.0, cy / max(1, bbox[3] - bbox[1])))


def _legacy_select_views(
    track: PalletTrack,
    min_views: int,
    target_views: int,
    max_views: int,
    blur_percentile: float,
    min_frame_gap_diversity: int,
    max_iou_suppress: float,
) -> List[PalletObservation]:
    """Algoritmo original por segmentos temporales (cuando enable_diversity=False)."""
    if not track.observations:
        return []
    scores = [o.blur_score if o.blur_score is not None else 0.0 for o in track.observations]
    threshold = float(np.quantile(scores, blur_percentile) if len(scores) > 1 else scores[0])
    filtered = [o for o in track.observations if (o.blur_score or 0.0) >= threshold]
    if not filtered:
        filtered = track.observations
    filtered.sort(key=lambda o: o.frame_idx)
    k = min(target_views, max_views, len(filtered))
    if k <= 0:
        return filtered[:max_views] if len(filtered) >= min_views else filtered
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
    if max_iou_suppress > 0 and min_frame_gap_diversity >= 0 and len(selected) > 1:
        selected.sort(key=lambda o: o.frame_idx)
        kept: List[PalletObservation] = []
        for cand in selected:
            too_similar = False
            for kk in kept:
                if abs(cand.frame_idx - kk.frame_idx) <= min_frame_gap_diversity and _bbox_iou(
                    cand.bbox, kk.bbox
                ) > max_iou_suppress:
                    too_similar = True
                    break
            if not too_similar:
                kept.append(cand)
        selected = kept
    return selected[:max_views]


def _diversity_select_views(
    track: PalletTrack,
    min_views: int,
    target_views: int,
    max_views: int,
    blur_percentile: float,
    min_frame_gap_diversity: int,
    max_iou_suppress: float,
    frame_width: Optional[int],
    frame_height: Optional[int],
    phash_near_dup_thr: int,
    centroid_near_dup_thr: float,
    anchor_window_frames: int,
    diversity_weight: float,
    return_debug: bool,
    phash_cache: Dict[str, Optional[str]],
) -> Tuple[List[PalletObservation], Optional[Dict[str, Any]]]:
    """Selección en 2 fases: anchors (early/mid/late) + greedy diversidad con phash/centroid dedup."""
    if not track.observations:
        return [], None if not return_debug else {"candidates": [], "selected": [], "discarded_reasons_count": {}}

    # 1) Candidatos con features
    blur_scores = [o.blur_score if o.blur_score is not None else 0.0 for o in track.observations]
    threshold = float(np.quantile(blur_scores, blur_percentile) if len(blur_scores) > 1 else blur_scores[0])
    valid_obs = [o for o in track.observations if (o.blur_score or 0.0) >= threshold]
    if not valid_obs:
        valid_obs = list(track.observations)
    valid_obs.sort(key=lambda o: o.frame_idx)

    candidates: List[Dict[str, Any]] = []
    for o in valid_obs:
        if not o.roi_path:
            continue
        area = _bbox_area(o.bbox)
        centroid = _centroid_normalized(o.bbox, frame_width, frame_height)
        w, h = max(1, o.bbox[2] - o.bbox[0]), max(1, o.bbox[3] - o.bbox[1])
        aspect_ratio = w / h
        phash_hex = _phash_for_roi(o.roi_path, phash_cache) if return_debug or diversity_weight > 0 else None
        candidates.append({
            "obs": o,
            "frame_idx": o.frame_idx,
            "roi_path": o.roi_path,
            "blur": o.blur_score or 0.0,
            "area": area,
            "centroid": centroid,
            "aspect_ratio": aspect_ratio,
            "phash": phash_hex,
        })

    if not candidates:
        return [], None if not return_debug else {"candidates": [], "selected": [], "discarded_reasons_count": {"no_roi": len(valid_obs)}}

    discarded_reasons_count: Dict[str, int] = {"no_roi": len(valid_obs) - len(candidates), "too_blurry": 0, "near_dup_phash": 0, "near_dup_centroid": 0, "fails_gap": 0, "other": 0}
    blurs = [c["blur"] for c in candidates]
    areas = [c["area"] for c in candidates]
    b_min, b_max = min(blurs), max(blurs)
    a_min, a_max = min(areas), max(areas)
    for c in candidates:
        norm_b = (c["blur"] - b_min) / (b_max - b_min + 1e-9)
        norm_a = (c["area"] - a_min) / (a_max - a_min + 1e-9)
        c["base_score"] = 0.6 * norm_b + 0.4 * norm_a

    frame_indices = [c["frame_idx"] for c in candidates]
    f_min, f_max = min(frame_indices), max(frame_indices)
    n_cand = len(candidates)

    # 2) Fase 1: anchors (early, mid, late)
    selected: List[Dict[str, Any]] = []
    selected_obs: List[PalletObservation] = []
    reasons: Dict[int, str] = {}
    window = anchor_window_frames
    anchor_positions = []
    if n_cand >= 3:
        for name, frac_start, frac_end in [
            ("early", 0.0, 1.0 / 3.0),
            ("mid", 1.0 / 3.0, 2.0 / 3.0),
            ("late", 2.0 / 3.0, 1.0),
        ]:
            low = f_min + (f_max - f_min) * frac_start
            high = f_min + (f_max - f_min) * frac_end
            in_window = [c for c in candidates if low <= c["frame_idx"] <= high and c["obs"] not in selected_obs]
            if not in_window:
                continue
            best = max(in_window, key=lambda c: c["base_score"])
            # tie-break: prefer one within ±window of segment center
            center_f = (low + high) / 2
            in_window.sort(key=lambda c: (c["base_score"], -abs(c["frame_idx"] - center_f)), reverse=True)
            best = in_window[0]
            if best["obs"] not in selected_obs:
                best["reason"] = f"anchor_{name}"
                selected.append(best)
                selected_obs.append(best["obs"])
                reasons[best["frame_idx"]] = best["reason"]
                anchor_positions.append(best["frame_idx"])

    # If we have fewer than 3 segments, pick best by base_score up to 3
    if len(selected) < 3:
        remaining = [c for c in candidates if c["obs"] not in selected_obs]
        remaining.sort(key=lambda c: c["base_score"], reverse=True)
        for c in remaining[: 3 - len(selected)]:
            c["reason"] = "anchor_fill"
            selected.append(c)
            selected_obs.append(c["obs"])
            reasons[c["frame_idx"]] = c["reason"]

    # 3) Fase 2: greedy diversity until target_views/max_views
    need = min(max_views, max(min_views, target_views)) - len(selected)

    while need > 0:
        remaining = [c for c in candidates if c["obs"] not in selected_obs]
        if not remaining:
            break
        best_cand = None
        best_total = -1.0
        for c in remaining:
            min_phash_d = 64
            min_centroid_d = 2.0
            min_frame_gap = 99999
            for s in selected:
                if c["phash"] and s.get("phash"):
                    d = _phash_dist_hex(c["phash"], s["phash"])
                    min_phash_d = min(min_phash_d, d)
                cx, cy = c["centroid"]
                sx, sy = s["centroid"]
                min_centroid_d = min(min_centroid_d, ((cx - sx) ** 2 + (cy - sy) ** 2) ** 0.5)
                min_frame_gap = min(min_frame_gap, abs(c["frame_idx"] - s["frame_idx"]))

            if min_phash_d <= phash_near_dup_thr:
                discarded_reasons_count["near_dup_phash"] += 1
                continue
            if min_centroid_d <= centroid_near_dup_thr:
                discarded_reasons_count["near_dup_centroid"] += 1
                continue
            if min_frame_gap < min_frame_gap_diversity:
                discarded_reasons_count["fails_gap"] += 1
                continue

            norm_phash = min(1.0, min_phash_d / 32.0)
            norm_centroid = min(1.0, min_centroid_d / 0.5)
            norm_gap = min(1.0, min_frame_gap / 30.0)
            diversity_bonus = (norm_phash + norm_centroid + norm_gap) / 3.0
            total = c["base_score"] + diversity_weight * diversity_bonus
            if total > best_total:
                best_total = total
                best_cand = c
                best_cand["min_phash_dist"] = min_phash_d
                best_cand["min_centroid_dist"] = min_centroid_d
                best_cand["min_frame_gap"] = min_frame_gap

        if best_cand is None:
            break
        best_cand["reason"] = "greedy_diverse"
        selected.append(best_cand)
        selected_obs.append(best_cand["obs"])
        reasons[best_cand["frame_idx"]] = best_cand["reason"]
        need -= 1

    # Apply max_iou_suppress / min_frame_gap on final list (same as legacy)
    selected_obs.sort(key=lambda o: o.frame_idx)
    if max_iou_suppress > 0 and min_frame_gap_diversity >= 0 and len(selected_obs) > 1:
        kept: List[PalletObservation] = []
        for cand in selected_obs:
            too_similar = False
            for kk in kept:
                if abs(cand.frame_idx - kk.frame_idx) <= min_frame_gap_diversity and _bbox_iou(cand.bbox, kk.bbox) > max_iou_suppress:
                    too_similar = True
                    break
            if not too_similar:
                kept.append(cand)
        selected_obs = kept

    out = selected_obs[:max_views]

    if not return_debug:
        return out, None

    debug: Dict[str, Any] = {
        "candidates": [
            {
                "frame_idx": c["frame_idx"],
                "blur": c["blur"],
                "area": c["area"],
                "centroid": c["centroid"],
                "aspect_ratio": c["aspect_ratio"],
                "base_score": round(c["base_score"], 4),
                "phash": c.get("phash"),
            }
            for c in candidates
        ],
        "selected": [
            {
                "frame_idx": c["frame_idx"],
                "roi_path": c["roi_path"],
                "reason": c.get("reason", "selected"),
                "min_phash_dist_to_selected": c.get("min_phash_dist"),
                "min_centroid_dist_to_selected": round(c.get("min_centroid_dist", 0), 4),
                "min_frame_gap_to_selected": c.get("min_frame_gap"),
            }
            for c in selected
        ],
        "discarded_reasons_count": discarded_reasons_count,
    }
    return out, debug


def select_views_per_track(
    track: PalletTrack,
    min_views: int,
    target_views: int,
    max_views: int,
    blur_percentile: float = 0.25,
    min_frame_gap_diversity: int = 3,
    max_iou_suppress: float = 0.8,
    frame_width: Optional[int] = None,
    frame_height: Optional[int] = None,
    enable_diversity: bool = True,
    phash_near_dup_thr: int = 4,
    centroid_near_dup_thr: float = 0.03,
    anchor_window_frames: int = 15,
    diversity_weight: float = 0.35,
    return_debug: bool = False,
    phash_cache: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[List[PalletObservation], Optional[Dict[str, Any]]]:
    """Selecciona las mejores vistas por track para enviar a Gemini.

    Con enable_diversity=True (default): selección en 2 fases (anchors early/mid/late
    + greedy diversidad) con dedup por phash y centroide. Con enable_diversity=False
    usa el algoritmo legacy por segmentos temporales.

    Returns:
        (views, debug_opt): lista de hasta max_views observaciones; debug_opt no None solo si return_debug=True.
    """
    if not enable_diversity:
        views = _legacy_select_views(
            track, min_views, target_views, max_views,
            blur_percentile, min_frame_gap_diversity, max_iou_suppress,
        )
        return (views, None)

    cache = phash_cache if phash_cache is not None else {}
    return _diversity_select_views(
        track,
        min_views,
        target_views,
        max_views,
        blur_percentile,
        min_frame_gap_diversity,
        max_iou_suppress,
        frame_width,
        frame_height,
        phash_near_dup_thr,
        centroid_near_dup_thr,
        anchor_window_frames,
        diversity_weight,
        return_debug,
        cache,
    )
