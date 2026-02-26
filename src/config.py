"""
Módulo de configuración del sistema.

Carga y valida la configuración desde variables de entorno,
con valores por defecto sensatos.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Cargar variables de entorno desde .env si existe
load_dotenv()


def _parse_max_frames_to_send() -> Optional[int]:
    """None = sin límite (procesar todo el video). Solo límite si se define explícitamente."""
    raw = os.getenv("MAX_FRAMES_TO_SEND", "").strip()
    if raw in ("", "0"):
        return None
    try:
        n = int(raw)
        return n if 1 <= n <= 10000 else None
    except ValueError:
        return None


def _parse_time_limit_sec() -> Optional[float]:
    raw = os.getenv("TIME_LIMIT_SEC", "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return None


class Settings(BaseModel):
    """Configuración del sistema de conteo de inventario por video.
    
    Todos los valores pueden ser configurados mediante variables de entorno
    o usando valores por defecto.
    """
    model_config = {"extra": "forbid"}

    # API Configuration
    gemini_api_key: str = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", ""),
        description="API key de Gemini. Requerida para usar el servicio.",
    )
    gemini_model_name: str = Field(
        default_factory=lambda: os.getenv(
            "GEMINI_MODEL_NAME", "gemini-2.0-flash-exp"
        ),
        description="Nombre del modelo de Gemini a usar.",
    )
    gemini_max_retries: int = Field(
        default_factory=lambda: int(os.getenv("GEMINI_MAX_RETRIES", "3")),
        ge=1,
        le=10,
        description="Número máximo de reintentos en llamadas a Gemini (1 a 10).",
    )
    gemini_retry_delay: float = Field(
        default_factory=lambda: float(os.getenv("GEMINI_RETRY_DELAY", "1.0")),
        ge=0.1,
        le=60.0,
        description="Espera inicial entre reintentos en segundos (0.1 a 60).",
    )

    # Frame Extraction Settings
    extract_fps: float = Field(
        default_factory=lambda: float(os.getenv("EXTRACT_FPS", "1.0")),
        ge=0.1,
        le=60.0,
        description="Frames por segundo a extraer del video (0.1 a 60).",
    )
    max_frames_to_send: Optional[int] = Field(
        default_factory=_parse_max_frames_to_send,
        description="Máximo de frames a enviar a Gemini (None = sin límite). Env: MAX_FRAMES_TO_SEND ('' o '0' = sin límite).",
    )
    frame_stride: int = Field(
        default_factory=lambda: int(os.getenv("FRAME_STRIDE", "1")),
        ge=1,
        le=1000,
        description="Cada cuántos frames tomar tras la selección (1 = todos). Acelera videos largos sin truncar por error.",
    )
    time_limit_sec: Optional[float] = Field(
        default_factory=_parse_time_limit_sec,
        description="Procesar solo frames con timestamp_seconds <= este valor. Env: TIME_LIMIT_SEC. None = sin límite.",
    )

    # Image Preprocessing (Bloque 7)
    resize_max_side: int = Field(
        default_factory=lambda: int(os.getenv("RESIZE_MAX_SIDE", "1280")),
        ge=320,
        le=4096,
        description="Tamaño máximo del lado de la imagen al redimensionar (320 a 4096 píxeles).",
    )
    jpeg_quality: int = Field(
        default_factory=lambda: int(os.getenv("JPEG_QUALITY", "85")),
        ge=1,
        le=100,
        description="Calidad JPEG al guardar frames (1 a 100).",
    )
    similarity_sample_size: int = Field(
        default_factory=lambda: int(os.getenv("SIMILARITY_SAMPLE_SIZE", "100")),
        ge=16,
        le=512,
        description="Tamaño de muestra para comparación en filtro de similitud (16 a 512).",
    )

    # Output Configuration
    output_dir: str = Field(
        default_factory=lambda: os.getenv("OUTPUT_DIR", "output"),
        description="Directorio donde se guardarán los resultados.",
    )
    debug_save_frames: bool = Field(
        default_factory=lambda: os.getenv("DEBUG_SAVE_FRAMES", "false").lower()
        in ("true", "1", "yes"),
        description="Si es True, guarda los frames procesados para debug.",
    )

    # Consolidation (Bloque 3)
    consolidation_mad_threshold: float = Field(
        default_factory=lambda: float(os.getenv("CONSOLIDATION_MAD_THRESHOLD", "3.0")),
        ge=0.5,
        le=10.0,
        description="Factor k para filtrado de outliers por MAD (0.5 a 10.0).",
    )
    consolidation_min_evidence_frames: int = Field(
        default_factory=lambda: int(os.getenv("CONSOLIDATION_MIN_EVIDENCE_FRAMES", "2")),
        ge=1,
        le=20,
        description="Mínimo de observaciones (inliers) para no descartar producto (1 a 20).",
    )
    consolidation_min_confidence: float = Field(
        default_factory=lambda: float(os.getenv("CONSOLIDATION_MIN_CONFIDENCE", "0.45")),
        ge=0.0,
        le=1.0,
        description="Mínima confianza final para no descartar producto fantasma (0 a 1).",
    )

    @field_validator("max_frames_to_send")
    @classmethod
    def validate_max_frames_to_send(cls, v: Optional[int]) -> Optional[int]:
        """None y 0 = sin límite. Si se define, debe estar en 1..10000."""
        if v is None or v == 0:
            return None
        if v < 1 or v > 10000:
            raise ValueError("max_frames_to_send debe ser None/0 (sin límite) o entre 1 y 10000")
        return v

    @field_validator("gemini_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Valida que la API key no esté vacía (aunque puede ser configurada después)."""
        if not v:
            # No lanzamos error aquí, solo advertimos
            # El error se lanzará cuando se intente usar el cliente
            pass
        return v

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v: str) -> str:
        """Normaliza el path del directorio de salida."""
        # Convertir a Path y luego a string para normalizar
        path = Path(v).expanduser().resolve()
        return str(path)

    def ensure_output_dir(self) -> Path:
        """Asegura que el directorio de salida existe y lo crea si es necesario.
        
        Returns:
            Path al directorio de salida.
        """
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path


# Instancia global de configuración (lazy loading)
_settings: Optional[Settings] = None


def load_settings() -> Settings:
    """Carga la configuración desde variables de entorno.
    
    La configuración se carga una vez y se cachea. Si necesitas
    recargar la configuración (por ejemplo, después de cambiar .env),
    usa reload_settings().
    
    Returns:
        Settings: Instancia de configuración.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Recarga la configuración desde variables de entorno.
    
    Útil cuando se cambia el archivo .env en tiempo de ejecución.
    
    Returns:
        Settings: Nueva instancia de configuración.
    """
    global _settings
    # Recargar variables de entorno
    load_dotenv(override=True)
    _settings = Settings()
    return _settings


def get_settings() -> Settings:
    """Obtiene la configuración actual (alias de load_settings para claridad).
    
    Returns:
        Settings: Instancia de configuración.
    """
    return load_settings()
