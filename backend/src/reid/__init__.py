"""
Re-ID: fusión de tracks por similitud visual (pHash/CLIP + DSU).

Sprint 6B — Solo activo cuando REID_ENABLED=True.
Flujo: build_track_signatures → generate_candidates → filter_with_phash → verify_with_clip → merge_tracks_dsu.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from src.models.schemas import PalletTrack
from src.reid.clip_embedder import verify_with_clip
from src.reid.gating import generate_candidates
from src.reid.merge import get_merge_map, merge_tracks_dsu
from src.reid.phash import filter_with_phash
from src.reid.signature import build_track_signatures

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)


def run_reid_pipeline(
    tracks: list[PalletTrack],
    settings: "Settings",
    video_width: Optional[int] = None,
    video_height: Optional[int] = None,
    *,
    embedder: Optional[Any] = None,
) -> tuple[list[PalletTrack], dict[str, Any]]:
    """Ejecuta el flujo Re-ID completo: firmas → gating → pHash → CLIP → merge.

    Con CLIP en stub (embedder=None) confirmed_pairs queda [] y no hay merges.
    Si ocurre una excepción se devuelven los tracks originales y métricas con reid_error.

    Args:
        tracks: Lista de tracks después de ROI+blur.
        settings: Configuración (reid_enabled ya comprobado por el caller).
        video_width: Ancho del video para centroides (opcional).
        video_height: Alto del video para centroides (opcional).

    Returns:
        (merged_tracks, metrics): tracks fusionados (o originales si error/stub) y métricas.
    """
    tracks_before_reid = len(tracks)
    metrics: dict[str, Any] = {
        "tracks_before_reid": tracks_before_reid,
        "tracks_after_reid": tracks_before_reid,
        "tracks_merged_count": 0,
        "reid_candidates_generated": 0,
        "reid_pairs_after_phash": 0,
        "reid_pairs_confirmed": 0,
        "clip_verifications_run": 0,
        "reid_signatures": {},
        "reid_candidates": [],
        "reid_merge_map": {},
    }
    try:
        if not tracks:
            return [], metrics

        signature_k = getattr(settings, "reid_signature_k", 2)
        signatures = build_track_signatures(
            tracks,
            signature_k=signature_k,
            frame_width=video_width,
            frame_height=video_height,
        )
        metrics["reid_signatures"] = {tid: sig.model_dump() for tid, sig in signatures.items()}
        metrics["tracks_with_signatures"] = sum(
            1 for sig in signatures.values() if len(sig.roi_phashes) > 0
        )

        max_gap = getattr(settings, "reid_max_gap_frames", 240)
        dx_max = getattr(settings, "reid_dx_max", 0.20)
        dy_max = getattr(settings, "reid_dy_max", 0.25)
        candidates = generate_candidates(
            signatures, max_gap_frames=max_gap, dx_max=dx_max, dy_max=dy_max
        )
        metrics["reid_candidates_generated"] = len(candidates)
        metrics["reid_candidates"] = [[a, b] for a, b in candidates]

        phash_max_dist = getattr(settings, "phash_max_dist", 10)
        pairs_after_phash = filter_with_phash(candidates, signatures, max_dist=phash_max_dist)
        metrics["reid_pairs_after_phash"] = len(pairs_after_phash)

        clip_min_sim = getattr(settings, "clip_min_sim", 0.92)
        confirmed_pairs = verify_with_clip(
            pairs_after_phash, signatures, min_sim=clip_min_sim, embedder=embedder
        )
        metrics["reid_pairs_confirmed"] = len(confirmed_pairs)
        metrics["clip_verifications_run"] = len(pairs_after_phash)

        merged_tracks = merge_tracks_dsu(tracks, confirmed_pairs)
        metrics["tracks_after_reid"] = len(merged_tracks)
        metrics["tracks_merged_count"] = tracks_before_reid - len(merged_tracks)
        metrics["reid_merge_map"] = get_merge_map(tracks, confirmed_pairs)

        return merged_tracks, metrics
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        logger.warning("Re-ID pipeline error, returning original tracks: %s", e)
        metrics["reid_error"] = str(e)
        metrics["tracks_after_reid"] = tracks_before_reid
        metrics["tracks_merged_count"] = 0
        return list(tracks), metrics


def run_reid_passthrough(
    tracks: list[PalletTrack],
    settings: "Settings",
    video_width: Optional[int] = None,
    video_height: Optional[int] = None,
) -> tuple[list[PalletTrack], dict[str, Any]]:
    """Deprecated: use run_reid_pipeline. Mantenido por compatibilidad."""
    return run_reid_pipeline(tracks, settings, video_width, video_height)
