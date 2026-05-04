"""
Tracker multi-objeto (Sprint A).

Asocia detecciones entre frames para obtener track_id estable.
Implementación mínima con asociación por IoU; se puede sustituir por ByteTrack/SORT.
"""

from src.models.schemas import BBox

# Salida: (bbox, track_id)
TrackedBBox = tuple[BBox, str]


def _iou_box(b1: BBox, b2: BBox) -> float:
    """IoU entre dos bboxes (x1, y1, x2, y2, conf). Usa solo x1,y1,x2,y2."""
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


class MultiObjectTracker:
    """Tracker simple por IoU. Mantiene track_id estable entre frames."""

    def __init__(
        self,
        min_hits: int = 3,
        max_age: int = 30,
        iou_threshold: float = 0.3,
    ):
        self.min_hits = min_hits
        self.max_age = max_age
        self.iou_threshold = iou_threshold
        self._next_id = 0
        # track_id -> [(frame_idx, bbox), ...]
        self._tracks: dict[str, list[tuple[int, BBox]]] = {}
        # frame_idx -> [(bbox, track_id), ...]
        self._history: dict[int, list[TrackedBBox]] = {}
        self._last_frame_idx: int = -1

    def update(self, detections: list[BBox], frame_idx: int) -> list[TrackedBBox]:
        """Asocia detecciones al frame y devuelve (bbox, track_id) para este frame."""
        # Envejecer tracks: eliminar los que llevan más de max_age frames sin ver
        self._last_frame_idx = frame_idx
        to_drop = [
            tid
            for tid, obs in self._tracks.items()
            if obs and frame_idx - obs[-1][0] > self.max_age
        ]
        for tid in to_drop:
            del self._tracks[tid]

        if not detections:
            self._history[frame_idx] = []
            return []

        # Último bbox por track (para matching)
        last_bbox: dict[str, BBox] = {tid: obs[-1][1] for tid, obs in self._tracks.items() if obs}
        used_tracks: set = set()
        out: list[TrackedBBox] = []

        # Asignar cada detección al track con mayor IoU por encima del umbral
        for bbox in detections:
            best_id: str | None = None
            best_iou = self.iou_threshold
            for tid, last in last_bbox.items():
                if tid in used_tracks:
                    continue
                iou = _iou_box(bbox, last)
                if iou > best_iou:
                    best_iou = iou
                    best_id = tid
            if best_id is not None:
                used_tracks.add(best_id)
                self._tracks[best_id].append((frame_idx, bbox))
                out.append((bbox, best_id))
            else:
                new_id = str(self._next_id)
                self._next_id += 1
                self._tracks[new_id] = [(frame_idx, bbox)]
                out.append((bbox, new_id))

        self._history[frame_idx] = out
        return out

    def get_tracks(self) -> dict[int, list[TrackedBBox]]:
        """Devuelve el historial: frame_idx -> [(bbox, track_id), ...]."""
        return dict(self._history)
