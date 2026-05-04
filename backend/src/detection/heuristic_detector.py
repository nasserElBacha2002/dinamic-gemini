"""
Detector heurístico de pallets (sin ML) para MVP Sprint A.

Pipeline OpenCV: resize (opcional) → blur → Canny → morfología → contornos
→ filtrado por área/aspect ratio → top-K por área → NMS por IoU.
"""

from typing import Optional

import cv2
import numpy as np

from src.models.schemas import BBox


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """IoU entre dos bboxes (x1, y1, x2, y2)."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    ab = (b[2] - b[0]) * (b[3] - b[1])
    union = aa + ab - inter
    return inter / union if union > 0 else 0.0


def _nms_bboxes(
    bboxes: list[tuple[float, float, float, float, float]],
    iou_threshold: float,
) -> list[BBox]:
    """Suprime cajas con IoU > iou_threshold (mantiene orden por área)."""
    if not bboxes:
        return []
    kept: list[BBox] = []
    for b in bboxes:
        box = (b[0], b[1], b[2], b[3])
        overlap = False
        for k in kept:
            if _iou(box, (k[0], k[1], k[2], k[3])) > iou_threshold:
                overlap = True
                break
        if not overlap:
            kept.append(b)
    return kept


def detect_pallets_heuristic(
    frame: np.ndarray,
    min_area_ratio: float = 0.05,
    aspect_ratio_min: float = 0.6,
    aspect_ratio_max: float = 2.5,
    max_detections: int = 3,
    iou_nms_threshold: float = 0.5,
    resize_max_side: Optional[int] = None,
    confidence: float = 0.85,
) -> list[BBox]:
    """Detecta regiones tipo pallet por contornos (OpenCV, sin ML).

    Args:
        frame: Imagen BGR (H, W, C).
        min_area_ratio: Área mínima del contorno como fracción del área del frame.
        aspect_ratio_min: Mínimo ancho/alto del bbox del contorno.
        aspect_ratio_max: Máximo ancho/alto del bbox del contorno.
        max_detections: Máximo de bboxes a devolver (top por área).
        iou_nms_threshold: IoU umbral para NMS (suprimir duplicados).
        resize_max_side: Si no None, redimensionar lado mayor a este valor para procesar.
        confidence: Confianza fija asignada a cada detección heurística.

    Returns:
        Lista de bboxes (x1, y1, x2, y2, confidence) en coordenadas del frame original.
    """
    if frame is None or frame.size == 0:
        return []
    h0, w0 = frame.shape[0], frame.shape[1]
    frame_area = h0 * w0
    work = frame

    if resize_max_side and resize_max_side > 0 and max(h0, w0) > resize_max_side:
        if w0 >= h0:
            nw, nh = resize_max_side, int(h0 * resize_max_side / w0)
        else:
            nh, nw = resize_max_side, int(w0 * resize_max_side / h0)
        nw, nh = max(1, nw), max(1, nh)
        work = cv2.resize(work, (nw, nh), interpolation=cv2.INTER_AREA)
        scale_x, scale_y = w0 / nw, h0 / nh
        frame_area = nw * nh
    else:
        scale_x = scale_y = 1.0

    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    # Canny (50, 150) y kernel (15, 15) fijos; en producción se pueden exponer por config si se requiere tunear
    edges = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    dilated = cv2.dilate(closed, kernel)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates: list[tuple[float, float, float, float, float]] = []
    min_area = frame_area * min_area_ratio
    h_work, w_work = work.shape[0], work.shape[1]
    min_side = max(20, int(min(w_work, h_work) * 0.02))

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw < min_side or bh < min_side:
            continue
        ar = bw / bh if bh > 0 else 0
        if not (aspect_ratio_min <= ar <= aspect_ratio_max):
            continue
        x2_br, y2_br = x + bw, y + bh
        candidates.append((float(x), float(y), float(x2_br), float(y2_br), confidence))

    candidates.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    candidates = candidates[: max_detections * 2]
    candidates = _nms_bboxes(candidates, iou_nms_threshold)[:max_detections]

    out: list[BBox] = []
    for x1f, y1f, x2f, y2f, conf in candidates:
        if scale_x != 1.0 or scale_y != 1.0:
            x1, y1 = x1f * scale_x, y1f * scale_y
            x2, y2 = x2f * scale_x, y2f * scale_y
        else:
            x1, y1, x2, y2 = x1f, y1f, x2f, y2f
        out.append((x1, y1, x2, y2, conf))
    return out
