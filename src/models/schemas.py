"""
Modelos Pydantic para el sistema de conteo de inventario por video.

Este módulo define todos los esquemas de datos usados en el sistema:
- Modelos minificados para la API de Gemini (optimización de costo)
- Modelos de metadata (video, frames)
- Modelos de salida simple (FinalResult)
- Modelos internos para consolidación (LLM observations, Consolidated)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, ConfigDict, field_validator

# ----------------------------
# Helpers
# ----------------------------
def clamp01(x: float) -> float:
    """Asegura que un valor esté en el rango [0.0, 1.0]."""
    return max(0.0, min(1.0, x))


# ----------------------------
# Minimal models for JSON API Output (Cost optimization)
# ----------------------------
class MinifiedProduct(BaseModel):
    """Modelo ultracompacto SOLO para el JSON de salida de Gemini.
    
    Usa claves cortas para minimizar el tamaño del JSON y reducir costos.
    Incluye campo de razonamiento (r) para que el modelo explique su lógica matemática.
    """
    model_config = ConfigDict(extra="forbid")

    # Claves minificadas (b: brand, n: product, r: reasoning, q: quantity, c: confidence)
    b: Optional[str] = Field(None, description="Marca del producto (opcional).")
    n: str = Field(..., description="Nombre o descripción del producto.")
    r: str = Field(..., description="Razonamiento matemático: e.g., 'Base 3x4=12. 2 layers=24. Top layer missing 3. 24-3=21'")
    q: int = Field(..., ge=0, description="Cantidad estimada de cajas.")
    c: float = Field(..., ge=0, le=1, description="Nivel de confianza (0 a 1).")

    @field_validator("c")
    @classmethod
    def _conf_01(cls, v: float) -> float:
        """Valida y ajusta la confianza al rango [0, 1]."""
        return clamp01(v)


class MinifiedPallet(BaseModel):
    """Modelo ultracompacto para un Pallet SOLO para la salida de Gemini."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Identificador único del pallet.")
    p: List[MinifiedProduct] = Field(..., description="Lista de productos en el pallet.")


class MinifiedFrameResult(BaseModel):
    """El objeto JSON completo que Gemini debe devolver para un frame."""
    model_config = ConfigDict(extra="forbid")

    pallets: List[MinifiedPallet] = Field(..., description="Lista de pallets detectados.")


# ----------------------------
# Sprint A: Detection, tracking, view selection
# ----------------------------
# BBox: (x1, y1, x2, y2, confidence) en píxeles; confidence en [0, 1]
BBox = Tuple[float, float, float, float, float]


class PalletObservation(BaseModel):
    """Una observación de un pallet en un frame (Sprint A)."""
    model_config = ConfigDict(extra="forbid")

    frame_idx: int = Field(..., ge=0, description="Índice del frame.")
    timestamp_seconds: float = Field(..., ge=0, description="Timestamp en segundos.")
    bbox: Tuple[int, int, int, int] = Field(..., description="Bounding box (x1, y1, x2, y2).")
    det_conf: float = Field(..., ge=0, le=1, description="Confianza de la detección.")
    blur_score: Optional[float] = Field(default=None, description="Nitidez del ROI (Laplacian var).")
    roi_path: Optional[str] = Field(default=None, description="Ruta al ROI guardado.")
    track_id: str = Field(..., description="ID estable del track.")


class PalletTrack(BaseModel):
    """Track estable de un pallet a lo largo de frames (Sprint A)."""
    model_config = ConfigDict(extra="forbid")

    track_id: str = Field(..., description="ID único del track.")
    observations: List[PalletObservation] = Field(..., description="Observaciones del pallet.")
    start_frame: int = Field(..., ge=0, description="Primer frame del track.")
    end_frame: int = Field(..., ge=0, description="Último frame del track.")

    def best_views(self, k: int) -> List[PalletObservation]:
        """Selecciona hasta k mejores vistas por blur_score y diversidad temporal (ordenadas)."""
        if not self.observations or k <= 0:
            return []
        sorted_obs = sorted(
            self.observations,
            key=lambda o: (o.blur_score or 0.0, -(o.bbox[2] - o.bbox[0]) * (o.bbox[3] - o.bbox[1])),
            reverse=True,
        )
        return sorted_obs[:k]

    def roi_paths_for_views(self, k: int) -> List[str]:
        """Rutas ROI de las k mejores vistas (excluye observaciones sin roi_path)."""
        views = self.best_views(k)
        return [o.roi_path for o in views if o.roi_path]


# ----------------------------
# Core metadata
# ----------------------------
class VideoMetadata(BaseModel):
    """Metadata de un video procesado."""
    model_config = ConfigDict(extra="forbid")

    video_id: str
    file_path: str
    duration_seconds: float = Field(..., gt=0, description="Duración del video en segundos.")
    fps: float = Field(..., gt=0, description="Frames por segundo del video.")
    width: int = Field(..., gt=0, description="Ancho del video en píxeles.")
    height: int = Field(..., gt=0, description="Alto del video en píxeles.")


class FrameRef(BaseModel):
    """Referencia a un frame extraído del video."""
    model_config = ConfigDict(extra="forbid")

    frame_idx: int = Field(..., ge=0, description="Índice del frame en el video.")
    timestamp_seconds: float = Field(..., ge=0, description="Timestamp del frame en segundos.")
    image_path: Optional[str] = Field(
        default=None, description="Ruta al archivo de imagen si fue guardado a disco."
    )
    width: Optional[int] = Field(default=None, gt=0, description="Ancho del frame en píxeles.")
    height: Optional[int] = Field(default=None, gt=0, description="Alto del frame en píxeles.")


# ----------------------------
# Minimal output you want (simple)
# ----------------------------
class ProductEstimate(BaseModel):
    """Estimación de cantidad de cajas para un producto."""
    model_config = ConfigDict(extra="forbid")

    brand: Optional[str] = Field(default=None, description="Marca del producto (opcional).")
    product: str = Field(..., description="Nombre o descripción del producto.")
    estimated_boxes: int = Field(..., ge=0, description="Cantidad estimada de cajas.")
    confidence: float = Field(..., ge=0, le=1, description="Nivel de confianza (0 a 1).")

    @field_validator("confidence")
    @classmethod
    def _conf_01(cls, v: float) -> float:
        """Valida y ajusta la confianza al rango [0, 1]."""
        return clamp01(v)


class PalletEstimate(BaseModel):
    """Estimación de productos en un pallet."""
    model_config = ConfigDict(extra="forbid")

    pallet_id: str = Field(..., description="Identificador único del pallet.")
    products: List[ProductEstimate] = Field(..., description="Lista de productos en el pallet.")


class FinalResult(BaseModel):
    """
    Este es el contrato FINAL del sistema: simple, barato, directo.
    
    Este es el formato de salida que se exporta como JSON final.
    """
    model_config = ConfigDict(extra="forbid")

    video_id: str = Field(..., description="Identificador del video procesado.")
    pallets: List[PalletEstimate] = Field(..., description="Lista de pallets detectados.")
    # opcional pero útil para debug/observabilidad
    processing_summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Resumen del procesamiento (tiempos, frames, etc.). "
            "Nota: 'frames_analyzed' = número de frames enviados a Gemini (puede ser menor que frames_selected si max_frames_to_send trunca)."
        ),
    )


# ----------------------------
# Detailed internal LLM outputs (para consolidación)
# ----------------------------
class LLMProductObservation(BaseModel):
    """
    Lo que el LLM "cree" ver en un frame para un producto.
    
    Este modelo se usa internamente para almacenar observaciones individuales
    antes de consolidarlas.
    """
    model_config = ConfigDict(extra="forbid")

    product: str = Field(..., description="Nombre o descripción del producto.")
    brand: Optional[str] = Field(default=None, description="Marca del producto (opcional).")
    estimated_boxes: int = Field(..., ge=0, description="Cantidad estimada de cajas.")
    confidence: float = Field(..., ge=0, le=1, description="Nivel de confianza (0 a 1).")
    reasoning: Optional[str] = Field(default=None, description="Razonamiento matemático del modelo para llegar al conteo.")

    @field_validator("confidence")
    @classmethod
    def _conf_01(cls, v: float) -> float:
        """Valida y ajusta la confianza al rango [0, 1]."""
        return clamp01(v)


class LLMPalletObservation(BaseModel):
    """Observación de un pallet por el LLM en un frame."""
    model_config = ConfigDict(extra="forbid")

    pallet_id: str = Field(..., description="Identificador único del pallet.")
    products: List[LLMProductObservation] = Field(..., description="Lista de productos observados.")


class LLMFrameResult(BaseModel):
    """
    Resultado del LLM para 1 frame.
    
    Contiene todas las observaciones del LLM para un frame específico,
    incluyendo la respuesta cruda para debugging.
    """
    model_config = ConfigDict(extra="forbid")

    frame: FrameRef = Field(..., description="Referencia al frame procesado.")
    pallets: List[LLMPalletObservation] = Field(
        ..., description="Lista de pallets detectados en este frame."
    )
    raw_text: Optional[str] = Field(
        default=None, description="Respuesta cruda del LLM (útil para debug)."
    )
    model_name: Optional[str] = Field(
        default=None, description="Nombre del modelo de Gemini usado."
    )


# ----------------------------
# Consolidation outputs (auditables)
# ----------------------------
class ConsolidationStats(BaseModel):
    """Estadísticas de la consolidación de observaciones."""
    model_config = ConfigDict(extra="forbid")

    n_observations: int = Field(..., ge=0, description="Número total de observaciones.")
    n_inliers: Optional[int] = Field(
        default=None, description="Número de observaciones después de filtrar outliers."
    )
    min_est: Optional[int] = Field(default=None, description="Estimación mínima.")
    max_est: Optional[int] = Field(default=None, description="Estimación máxima.")
    median_est: Optional[float] = Field(default=None, description="Mediana de las estimaciones.")
    mad: Optional[float] = Field(
        default=None, description="Median Absolute Deviation (desviación absoluta mediana) de todas las observaciones."
    )
    mad_inliers: Optional[float] = Field(
        default=None, description="MAD de los inliers (después de filtrar outliers)."
    )
    conf_mean: Optional[float] = Field(
        default=None, description="Confianza media de los inliers."
    )
    stability_factor: Optional[float] = Field(
        default=None, description="Factor de estabilidad calculado."
    )
    coverage_factor: Optional[float] = Field(
        default=None, description="Factor de cobertura calculado."
    )


class ConsolidatedProduct(BaseModel):
    """Producto consolidado después de procesar múltiples frames."""
    model_config = ConfigDict(extra="forbid")

    product: str = Field(..., description="Nombre o descripción del producto.")
    brand: Optional[str] = Field(default=None, description="Marca del producto (opcional).")
    estimated_boxes: int = Field(..., ge=0, description="Cantidad estimada de cajas (consolidada).")
    confidence: float = Field(..., ge=0, le=1, description="Nivel de confianza final (0 a 1).")
    evidence_frames: int = Field(
        ..., ge=0, description="Número de frames que aportaron evidencia."
    )
    stats: Optional[ConsolidationStats] = Field(
        default=None, description="Estadísticas de la consolidación."
    )

    @field_validator("confidence")
    @classmethod
    def _conf_01(cls, v: float) -> float:
        """Valida y ajusta la confianza al rango [0, 1]."""
        return clamp01(v)


class ConsolidatedPallet(BaseModel):
    """Pallet consolidado después de procesar múltiples frames."""
    model_config = ConfigDict(extra="forbid")

    pallet_id: str = Field(..., description="Identificador único del pallet.")
    products: List[ConsolidatedProduct] = Field(..., description="Lista de productos consolidados.")


class ConsolidatedResult(BaseModel):
    """
    Resultado consolidado (interno).
    
    Este es el resultado después de consolidar todas las observaciones
    de múltiples frames. Luego se mapea a FinalResult para el output final.
    """
    model_config = ConfigDict(extra="forbid")

    video_id: str = Field(..., description="Identificador del video procesado.")
    pallets: List[ConsolidatedPallet] = Field(..., description="Lista de pallets consolidados.")
