"""
Gating temporal y espacial para candidatos Re-ID (Sprint 6B).

US-6B.3: generate_candidates con gap en frames y centroides normalizados (cx, cy en 0..1).
"""

from typing import Any, Dict, List, Optional, Tuple

from src.reid.signature import TrackSignature


def _gap_frames(sa: TrackSignature, sb: TrackSignature) -> Optional[int]:
    """Gap en frames entre dos tracks. None si faltan start/end."""
    if sa.start_frame is None or sa.end_frame is None or sb.start_frame is None or sb.end_frame is None:
        return None
    # A termina antes de que B empiece
    if sa.end_frame <= sb.start_frame:
        return sb.start_frame - sa.end_frame
    # B termina antes de que A empiece
    if sb.end_frame <= sa.start_frame:
        return sa.start_frame - sb.end_frame
    # Solapan
    return 0


def _spatial_ok(
    end_centroid: Tuple[float, float],
    start_centroid: Tuple[float, float],
    dx_max: float,
    dy_max: float,
) -> bool:
    """True si |end - start| está dentro de umbrales en x e y."""
    return (
        abs(end_centroid[0] - start_centroid[0]) <= dx_max
        and abs(end_centroid[1] - start_centroid[1]) <= dy_max
    )


def generate_candidates(
    signatures: Dict[str, TrackSignature],
    max_gap_frames: int = 240,
    dx_max: float = 0.20,
    dy_max: float = 0.25,
) -> List[Tuple[str, str]]:
    """Genera pares (track_id_a, track_id_b) candidatos a merge por gating temporal y espacial.

    - Temporal: 0 <= gap_frames <= max_gap_frames (gap = distancia entre end de uno y start del otro).
    - Espacial: |end_centroid_A - start_centroid_B| <= (dx_max, dy_max) cuando A termina antes que B,
      y simétrico cuando B termina antes que A. Si hay solapamiento (gap=0), se exige simetría:
      ambas direcciones (endA->startB y endB->startA) deben pasar el umbral.
    - Orden canónico: (min_id, max_id) para no duplicar (A,B) y (B,A).

    Si faltan start_frame, end_frame o centroides necesarios, el par se descarta.

    Args:
        signatures: Dict track_id -> TrackSignature (con start_frame, end_frame, start_centroid, end_centroid).
        max_gap_frames: Gap máximo en frames entre tracks.
        dx_max: Diferencia máxima en x normalizada (0..1).
        dy_max: Diferencia máxima en y normalizada (0..1).

    Returns:
        Lista de (track_id_a, track_id_b) con orden canónico (min_id, max_id).
    """
    ids = list(signatures.keys())
    n = len(ids)
    if n < 2:
        return []

    # Pre-filtro por ventana temporal si n grande (considera start y end para reducir falsos negativos)
    if n > 500:
        bucket_size = max(1, max_gap_frames * 2)
        by_start: Dict[int, List[str]] = {}
        by_end: Dict[int, List[str]] = {}
        for tid in ids:
            sig = signatures[tid]
            if sig.start_frame is not None:
                b = sig.start_frame // bucket_size
                by_start.setdefault(b, []).append(tid)
            if sig.end_frame is not None:
                b = sig.end_frame // bucket_size
                by_end.setdefault(b, []).append(tid)
        id_pairs_to_check = []
        seen = set()
        buckets = sorted(set(by_start.keys()) | set(by_end.keys()))
        for b in buckets:
            for b_other in (b - 1, b, b + 1):
                for tid_a in by_start.get(b, []):
                    for tid_b in by_end.get(b_other, []):
                        if tid_a == tid_b:
                            continue
                        canonical = (min(tid_a, tid_b), max(tid_a, tid_b))
                        if canonical not in seen:
                            seen.add(canonical)
                            id_pairs_to_check.append(canonical)
                for tid_a in by_end.get(b, []):
                    for tid_b in by_start.get(b_other, []):
                        if tid_a == tid_b:
                            continue
                        canonical = (min(tid_a, tid_b), max(tid_a, tid_b))
                        if canonical not in seen:
                            seen.add(canonical)
                            id_pairs_to_check.append(canonical)
    else:
        id_pairs_to_check = [(ids[i], ids[j]) for i in range(n) for j in range(i + 1, n)]

    out: List[Tuple[str, str]] = []
    for (tid_a, tid_b) in id_pairs_to_check:
        sa = signatures[tid_a]
        sb = signatures[tid_b]
        gap = _gap_frames(sa, sb)
        if gap is None:
            continue
        if gap < 0 or gap > max_gap_frames:
            continue

        if sa.start_centroid is None or sa.end_centroid is None or sb.start_centroid is None or sb.end_centroid is None:
            continue

        if gap == 0:
            ok = _spatial_ok(sa.end_centroid, sb.start_centroid, dx_max, dy_max) and _spatial_ok(
                sb.end_centroid, sa.start_centroid, dx_max, dy_max
            )
        elif sa.end_frame is not None and sb.start_frame is not None and sa.end_frame <= sb.start_frame:
            ok = _spatial_ok(sa.end_centroid, sb.start_centroid, dx_max, dy_max)
        else:
            ok = _spatial_ok(sb.end_centroid, sa.start_centroid, dx_max, dy_max)

        if not ok:
            continue

        canonical = (min(tid_a, tid_b), max(tid_a, tid_b))
        out.append(canonical)

    return out
