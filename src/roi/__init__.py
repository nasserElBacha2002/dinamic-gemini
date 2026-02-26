"""
Módulo ROI: recorte y calidad (Sprint A).

Responsabilidades:
- Recortar ROI con padding y redimensionar
- Calcular blur score (nitidez) del ROI
"""

from src.roi.cropper import crop_roi
from src.roi.quality import calculate_blur_score

__all__ = ["crop_roi", "calculate_blur_score"]
