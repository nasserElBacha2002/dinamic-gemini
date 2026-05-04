"""
Detección de pallets por frame (Sprint A).

Modos: stub (sin detecciones), heuristic (OpenCV sin ML), synthetic (2 bboxes fijos).
Opción A (MVP): heuristic o YOLO+clustering. Opción B: detector entrenado.
"""

from typing import TYPE_CHECKING, Optional

import numpy as np

from src.models.schemas import BBox

if TYPE_CHECKING:
    from src.config import Settings


def detect_pallets_per_frame(
    frame: np.ndarray,
    conf_threshold: float = 0.5,
    use_synthetic: bool = False,
    settings: Optional["Settings"] = None,
) -> list[BBox]:
    """Detecta pallets en un frame y devuelve bboxes con confianza.

    Args:
        frame: Imagen BGR (H, W, C).
        conf_threshold: Umbral mínimo de confianza (0 a 1). Detecciones por debajo se descartan.
        use_synthetic: Si True, devuelve 2 bboxes fijos (anula detector_mode).
        settings: Configuración; si se pasa y detector_mode=heuristic, usa detector heurístico.

    Returns:
        Lista de bboxes (x1, y1, x2, y2, confidence). Lista vacía en stub.

    Raises:
        ValueError: Si frame está vacío o conf_threshold fuera de rango.
    """
    if frame is None or frame.size == 0:
        raise ValueError("frame no puede estar vacío")
    if not 0.0 <= conf_threshold <= 1.0:
        raise ValueError(f"conf_threshold debe estar en [0, 1], recibido: {conf_threshold}")

    if use_synthetic:
        h, w = frame.shape[0], frame.shape[1]
        conf = max(conf_threshold, 0.9)
        left = (0.05 * w, 0.15 * h, 0.48 * w, 0.85 * h, conf)
        right = (0.52 * w, 0.15 * h, 0.95 * w, 0.85 * h, conf)
        return [left, right]

    mode = (settings.detector_mode or "stub").strip().lower() if settings else "stub"
    if mode == "heuristic" and settings is not None:
        from src.detection.heuristic_detector import detect_pallets_heuristic

        bboxes = detect_pallets_heuristic(
            frame,
            min_area_ratio=settings.heuristic_min_area_ratio,
            aspect_ratio_min=settings.heuristic_aspect_ratio_min,
            aspect_ratio_max=settings.heuristic_aspect_ratio_max,
            max_detections=settings.heuristic_max_detections_per_frame,
            iou_nms_threshold=settings.heuristic_iou_nms_threshold,
            resize_max_side=settings.heuristic_resize_max_side,
            confidence=max(conf_threshold, 0.85),
        )
        return bboxes

    return []
