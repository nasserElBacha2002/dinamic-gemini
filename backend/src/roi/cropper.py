"""
Recorte de ROI con padding y redimensionado (Sprint A).
"""

from pathlib import Path
from typing import Tuple

import cv2
import numpy as np


def crop_roi(
    bbox: Tuple[int, int, int, int],
    frame: np.ndarray,
    padding_pct: float,
    max_side: int,
    quality: int,
    output_path: str | None = None,
) -> Tuple[np.ndarray, str]:
    """Recorta el ROI con padding, redimensiona y opcionalmente guarda como JPEG.

    Args:
        bbox: (x1, y1, x2, y2) en píxeles.
        frame: Imagen BGR (H, W, C).
        padding_pct: Padding como fracción del lado mayor del bbox (ej. 0.12 = 12%).
        max_side: Lado máximo del ROI al redimensionar (mantiene aspect ratio).
        quality: Calidad JPEG (1-100) si se guarda.
        output_path: Si se indica, guarda el ROI en disco y devuelve esta ruta.

    Returns:
        (roi_array, path): ROI como array BGR y ruta (output_path si se guardó, si no "").

    Raises:
        ValueError: Si bbox inválido o quality fuera de rango.
    """
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"bbox inválido: x2>{x1}, y2>{y1} requerido")
    if not 0 <= quality <= 100:
        raise ValueError(f"quality debe estar en [0, 100], recibido: {quality}")

    h_img, w_img = frame.shape[:2]
    w_bbox = x2 - x1
    h_bbox = y2 - y1
    pad_px = int(max(w_bbox, h_bbox) * padding_pct)
    x1_p = max(0, x1 - pad_px)
    y1_p = max(0, y1 - pad_px)
    x2_p = min(w_img, x2 + pad_px)
    y2_p = min(h_img, y2 + pad_px)

    roi = frame[y1_p:y2_p, x1_p:x2_p]
    if roi.size == 0:
        raise ValueError("ROI vacío tras recorte")

    # Resize manteniendo aspect ratio (lado mayor = max_side)
    rh, rw = roi.shape[:2]
    if max(rh, rw) > max_side:
        scale = max_side / max(rh, rw)
        new_w = max(1, int(rw * scale))
        new_h = max(1, int(rh * scale))
        roi = cv2.resize(roi, (new_w, new_h), interpolation=cv2.INTER_AREA)

    path_out = ""
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(output_path, roi, [cv2.IMWRITE_JPEG_QUALITY, quality])
        path_out = output_path

    return roi, path_out
