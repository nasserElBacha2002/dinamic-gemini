"""
Orquestación del pipeline track-based (Sprint A).

Flujo: extracción → detección → tracking → ROI → blur → selección de vistas → Gemini (1 request/track).
"""

from src.pipeline.orchestrator import run_pipeline

__all__ = ["run_pipeline"]
