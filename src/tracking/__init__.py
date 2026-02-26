"""
Módulo de tracking multi-objeto (Sprint A).

Responsabilidades:
- Asociar detecciones entre frames para obtener track_id estable
- Construir PalletTrack a partir de la salida del tracker
"""

from src.tracking.track_builder import build_pallet_tracks
from src.tracking.tracker import MultiObjectTracker

__all__ = ["MultiObjectTracker", "build_pallet_tracks"]
