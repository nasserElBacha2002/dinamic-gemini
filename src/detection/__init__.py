"""
Módulo de detección de pallets por frame (Sprint A).

Responsabilidades:
- Detectar pallets (o cajas agrupadas) en cada frame
- Devolver bboxes con confianza para el tracker
"""

from src.detection.pallet_detector import detect_pallets_per_frame

__all__ = ["detect_pallets_per_frame"]
