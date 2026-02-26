"""
Construcción de PalletTrack a partir de la salida del tracker (Sprint A).
"""

from typing import Dict, List

from src.models.schemas import BBox, PalletObservation, PalletTrack
from src.tracking.tracker import TrackedBBox


def build_pallet_tracks(
    tracked_data: Dict[int, List[TrackedBBox]],
    video_fps: float = 30.0,
) -> List[PalletTrack]:
    """Convierte el historial del tracker en lista de PalletTrack.

    Args:
        tracked_data: frame_idx -> [(bbox, track_id), ...] (salida de MultiObjectTracker.get_tracks()).
        video_fps: FPS del video para calcular timestamp_seconds.

    Returns:
        Lista de PalletTrack con observaciones ordenadas por frame_idx.
    """
    if not tracked_data:
        return []

    # Agrupar por track_id: track_id -> [(frame_idx, bbox), ...]
    by_track: Dict[str, List[tuple[int, BBox]]] = {}
    for frame_idx, pairs in tracked_data.items():
        for bbox, track_id in pairs:
            by_track.setdefault(track_id, []).append((frame_idx, bbox))

    tracks: List[PalletTrack] = []
    for track_id, frame_bboxes in by_track.items():
        # Ordenar por frame_idx
        frame_bboxes.sort(key=lambda x: x[0])
        observations = [
            PalletObservation(
                frame_idx=frame_idx,
                timestamp_seconds=frame_idx / video_fps if video_fps > 0 else 0.0,
                bbox=(int(b[0]), int(b[1]), int(b[2]), int(b[3])),
                det_conf=float(b[4]),
                track_id=track_id,
            )
            for frame_idx, b in frame_bboxes
        ]
        if not observations:
            continue
        start_frame = observations[0].frame_idx
        end_frame = observations[-1].frame_idx
        tracks.append(
            PalletTrack(
                track_id=track_id,
                observations=observations,
                start_frame=start_frame,
                end_frame=end_frame,
            )
        )
    return tracks
