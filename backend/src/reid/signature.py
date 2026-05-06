"""
Firma por track para Re-ID (Sprint 6B).

US-6B.2: signature_k mejores ROIs por track, pHash por ROI, metadata para gating.
"""

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from src.models.schemas import PalletObservation, PalletTrack

logger = logging.getLogger(__name__)


class TrackSignature(BaseModel):
    """Firma mínima por track para Re-ID: pHashes de los K mejores ROIs + metadata para gating."""

    track_id: str = Field(..., description="ID del track.")
    roi_phashes: list[str] = Field(default_factory=list, description="Hashes pHash en hex por ROI.")
    roi_paths: list[str] = Field(
        default_factory=list, description="Paths de los ROIs usados (debug)."
    )
    signature_k: int = Field(..., description="K solicitado (puede haber menos si hay menos ROIs).")
    start_frame: Optional[int] = Field(None, description="Primer frame del track (vistas usadas).")
    end_frame: Optional[int] = Field(None, description="Último frame del track (vistas usadas).")
    start_centroid: Optional[tuple[float, float]] = Field(
        None,
        description="Centroide normalizado (cx, cy) en [0,1] al inicio del track; para gating espacial.",
    )
    end_centroid: Optional[tuple[float, float]] = Field(
        None,
        description="Centroide normalizado (cx, cy) en [0,1] al final del track; para gating espacial.",
    )


def _bbox_area(bbox: tuple[int, int, int, int]) -> int:
    return max(0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


def compute_phash(roi_path: str) -> Optional[str]:
    """Calcula pHash (64-bit) de una imagen y lo devuelve como string estable (hex).

    Args:
        roi_path: Ruta al archivo de imagen (ROI).

    Returns:
        String hex del hash, o None si no se pudo abrir/calcular.
    """
    try:
        import imagehash
        from PIL import Image

        path = Path(roi_path)
        if not path.exists():
            logger.debug("ROI no existe para phash: %s", roi_path)
            return None
        with Image.open(path) as img:
            img_rgb = img.convert("RGB").copy()
        phash = imagehash.phash(img_rgb)
        return str(phash)
    except Exception as e:
        logger.debug("Error calculando phash para %s: %s", roi_path, e)
        return None


def _select_best_rois(
    observations: list[PalletObservation],
    k: int,
) -> list[PalletObservation]:
    """Selecciona hasta k observaciones con roi_path, orden determinista: blur desc, area desc, frame_idx asc."""
    with_path = [o for o in observations if o.roi_path]
    if not with_path:
        return []

    def blur(o):
        return o.blur_score if o.blur_score is not None else 0.0

    def area(o):
        return _bbox_area(o.bbox)

    with_path.sort(key=lambda o: (-blur(o), -area(o), o.frame_idx))
    return with_path[:k]


def _bbox_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    """Centro del bbox (x_center, y_center)."""
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def build_track_signatures(
    tracks: list[PalletTrack],
    signature_k: int = 2,
    frame_width: Optional[int] = None,
    frame_height: Optional[int] = None,
) -> dict[str, TrackSignature]:
    """Construye una firma por track: K mejores ROIs por blur/área/frame, pHash y centroides para gating.

    Args:
        tracks: Tracks con observaciones (roi_path y blur_score recomendados).
        signature_k: Número de ROIs a usar por firma.
        frame_width: Ancho del frame para normalizar centroides (opcional).
        frame_height: Alto del frame para normalizar centroides (opcional).

    Returns:
        Dict track_id -> TrackSignature. Si frame_width/height no se pasan, start_centroid/end_centroid quedan None.
    """
    if signature_k < 1:
        signature_k = 1
    result: dict[str, TrackSignature] = {}
    for track in tracks:
        selected = _select_best_rois(track.observations, signature_k)
        roi_paths: list[str] = []
        roi_phashes: list[str] = []
        frames_used: list[int] = []
        for obs in selected:
            path = obs.roi_path
            if not path:
                continue
            h = compute_phash(path)
            if h is not None:
                roi_paths.append(path)
                roi_phashes.append(h)
                frames_used.append(obs.frame_idx)
        start_f = min(frames_used) if frames_used else track.start_frame
        end_f = max(frames_used) if frames_used else track.end_frame

        start_centroid: Optional[tuple[float, float]] = None
        end_centroid_val: Optional[tuple[float, float]] = None
        if (
            frame_width
            and frame_width > 0
            and frame_height
            and frame_height > 0
            and track.observations
        ):
            obs_by_start = min(track.observations, key=lambda o: abs(o.frame_idx - (start_f or 0)))
            obs_by_end = min(track.observations, key=lambda o: abs(o.frame_idx - (end_f or 0)))
            cx_s, cy_s = _bbox_center(obs_by_start.bbox)
            cx_e, cy_e = _bbox_center(obs_by_end.bbox)
            start_centroid = (
                max(0.0, min(1.0, cx_s / frame_width)),
                max(0.0, min(1.0, cy_s / frame_height)),
            )
            end_centroid_val = (
                max(0.0, min(1.0, cx_e / frame_width)),
                max(0.0, min(1.0, cy_e / frame_height)),
            )

        result[track.track_id] = TrackSignature(
            track_id=track.track_id,
            roi_phashes=roi_phashes,
            roi_paths=roi_paths,
            signature_k=signature_k,
            start_frame=start_f,
            end_frame=end_f,
            start_centroid=start_centroid,
            end_centroid=end_centroid_val,
        )
    return result
