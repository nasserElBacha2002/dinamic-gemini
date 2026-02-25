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

    # Frame Extraction Settings
    extract_fps: float = Field(
        default_factory=lambda: float(os.getenv("EXTRACT_FPS", "1.0")),
        ge=0.1,
        le=60.0,
        description="Frames por segundo a extraer del video (0.1 a 60).",
    )
    max_frames_to_send: int = Field(
        default_factory=lambda: int(os.getenv("MAX_FRAMES_TO_SEND", "10")),
        ge=1,
        le=100,
        description="Máximo número de frames a enviar a Gemini (1 a 100).",
    )

    # Image Preprocessing
    resize_max_side: int = Field(
        default_factory=lambda: int(os.getenv("RESIZE_MAX_SIDE", "1280")),
        ge=320,
        le=4096,
        description="Tamaño máximo del lado de la imagen al redimensionar (320 a 4096 píxeles).",
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
