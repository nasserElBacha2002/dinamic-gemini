"""
Cálculo de nitidez (blur score) del ROI (Sprint A).

Método: varianza del Laplaciano (mayor = más nítido).
"""

import cv2
import numpy as np


def calculate_blur_score(roi: np.ndarray) -> float:
    """Calcula un score de nitidez del ROI (varianza del Laplaciano).

    Args:
        roi: Imagen BGR (H, W, C).

    Returns:
        float >= 0. Valores mayores indican más nitidez.

    Raises:
        ValueError: Si roi está vacío.
    """
    if roi is None or roi.size == 0:
        raise ValueError("roi no puede estar vacío")
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if len(roi.shape) == 3 else roi
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(np.var(lap))
