"""
Tests unitarios para el módulo de configuración.

Verifica:
- Carga de configuración desde variables de entorno
- Valores por defecto
- Validación de campos
- Creación de directorio de salida
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import Settings, load_settings, reload_settings, get_settings


# ----------------------------
# Tests de valores por defecto
# ----------------------------
def test_settings_default_values():
    """Test que los valores por defecto son correctos."""
    # Limpiar variables de entorno para este test
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings()
        assert settings.extract_fps == 1.0
        assert settings.max_frames_to_send is None  # default: sin límite (procesar todo el video)
        assert settings.frame_stride == 1
        assert settings.time_limit_sec is None
        assert settings.resize_max_side == 1280
        assert settings.jpeg_quality == 85
        assert settings.similarity_sample_size == 100
        # output_dir se normaliza a path absoluto
        assert Path(settings.output_dir).resolve() == Path("output").resolve()
        assert settings.debug_save_frames is False
        assert settings.gemini_model_name == "gemini-2.0-flash-exp"
        assert settings.gemini_max_retries == 3
        assert settings.gemini_retry_delay == 1.0
        assert settings.gemini_api_key == ""
        assert settings.consolidation_mad_threshold == 3.0
        assert settings.consolidation_min_evidence_frames == 2
        assert settings.consolidation_min_confidence == 0.45


def test_settings_from_env():
    """Test que las variables de entorno se cargan correctamente."""
    env_vars = {
        "GEMINI_API_KEY": "test_api_key_123",
        "EXTRACT_FPS": "2.5",
        "MAX_FRAMES_TO_SEND": "20",
        "RESIZE_MAX_SIDE": "1920",
        "OUTPUT_DIR": "/tmp/test_output",
        "DEBUG_SAVE_FRAMES": "true",
        "GEMINI_MODEL_NAME": "gemini-pro",
        "GEMINI_MAX_RETRIES": "5",
        "GEMINI_RETRY_DELAY": "2.0",
        "CONSOLIDATION_MAD_THRESHOLD": "2.5",
        "CONSOLIDATION_MIN_EVIDENCE_FRAMES": "3",
        "CONSOLIDATION_MIN_CONFIDENCE": "0.5",
        "JPEG_QUALITY": "75",
        "SIMILARITY_SAMPLE_SIZE": "64",
        "FRAME_STRIDE": "5",
        "TIME_LIMIT_SEC": "60.5",
    }
    
    with patch.dict(os.environ, env_vars, clear=True):
        settings = Settings()
        assert settings.gemini_api_key == "test_api_key_123"
        assert settings.extract_fps == 2.5
        assert settings.max_frames_to_send == 20
        assert settings.frame_stride == 5
        assert settings.time_limit_sec == 60.5
        assert settings.resize_max_side == 1920
        assert settings.jpeg_quality == 75
        assert settings.similarity_sample_size == 64
        assert settings.output_dir == "/tmp/test_output"
        assert settings.debug_save_frames is True
        assert settings.gemini_model_name == "gemini-pro"
        assert settings.gemini_max_retries == 5
        assert settings.gemini_retry_delay == 2.0
        assert settings.consolidation_mad_threshold == 2.5
        assert settings.consolidation_min_evidence_frames == 3
        assert settings.consolidation_min_confidence == 0.5


# ----------------------------
# Tests de validación
# ----------------------------
def test_extract_fps_validation():
    """Test de validación de extract_fps."""
    # Valor válido
    settings = Settings(extract_fps=1.5)
    assert settings.extract_fps == 1.5
    
    # Valor fuera de rango (muy bajo)
    with pytest.raises(Exception):  # ValidationError de Pydantic
        Settings(extract_fps=0.05)
    
    # Valor fuera de rango (muy alto)
    with pytest.raises(Exception):
        Settings(extract_fps=100.0)


def test_max_frames_to_send_from_env_empty_or_zero_is_none():
    """MAX_FRAMES_TO_SEND '' o '0' = sin límite (procesar todo el video)."""
    for env_val in ("", "0", "  "):
        with patch.dict(os.environ, {"MAX_FRAMES_TO_SEND": env_val}, clear=False):
            settings = Settings()
            assert settings.max_frames_to_send is None


def test_max_frames_to_send_validation():
    """Test de validación de max_frames_to_send (None/0 = sin límite)."""
    # Valor válido
    settings = Settings(max_frames_to_send=15)
    assert settings.max_frames_to_send == 15
    # 0 se normaliza a None (sin límite)
    settings0 = Settings(max_frames_to_send=0)
    assert settings0.max_frames_to_send is None
    # Fuera de rango (1..10000)
    with pytest.raises(Exception):
        Settings(max_frames_to_send=10001)
    with pytest.raises(Exception):
        Settings(max_frames_to_send=-1)


def test_resize_max_side_validation():
    """Test de validación de resize_max_side."""
    # Valor válido
    settings = Settings(resize_max_side=1920)
    assert settings.resize_max_side == 1920
    
    # Valor fuera de rango (muy bajo)
    with pytest.raises(Exception):
        Settings(resize_max_side=100)
    
    # Valor fuera de rango (muy alto)
    with pytest.raises(Exception):
        Settings(resize_max_side=5000)


def test_jpeg_quality_validation():
    """Test de validación de jpeg_quality (Bloque 7)."""
    settings = Settings(jpeg_quality=90)
    assert settings.jpeg_quality == 90
    with pytest.raises(Exception):
        Settings(jpeg_quality=0)
    with pytest.raises(Exception):
        Settings(jpeg_quality=101)


def test_similarity_sample_size_validation():
    """Test de validación de similarity_sample_size (Bloque 7)."""
    settings = Settings(similarity_sample_size=128)
    assert settings.similarity_sample_size == 128
    with pytest.raises(Exception):
        Settings(similarity_sample_size=8)
    with pytest.raises(Exception):
        Settings(similarity_sample_size=1024)


def test_gemini_max_retries_validation():
    """Test de validación de gemini_max_retries (Bloque 8)."""
    settings = Settings(gemini_max_retries=5)
    assert settings.gemini_max_retries == 5
    with pytest.raises(Exception):
        Settings(gemini_max_retries=0)
    with pytest.raises(Exception):
        Settings(gemini_max_retries=11)


def test_gemini_retry_delay_validation():
    """Test de validación de gemini_retry_delay (Bloque 8)."""
    settings = Settings(gemini_retry_delay=2.0)
    assert settings.gemini_retry_delay == 2.0
    with pytest.raises(Exception):
        Settings(gemini_retry_delay=0.05)
    with pytest.raises(Exception):
        Settings(gemini_retry_delay=61.0)


def test_debug_save_frames_boolean():
    """Test que debug_save_frames acepta diferentes formatos booleanos."""
    env_vars_true = [
        {"DEBUG_SAVE_FRAMES": "true"},
        {"DEBUG_SAVE_FRAMES": "True"},
        {"DEBUG_SAVE_FRAMES": "1"},
        {"DEBUG_SAVE_FRAMES": "yes"},
        {"DEBUG_SAVE_FRAMES": "YES"},
    ]
    
    for env_var in env_vars_true:
        with patch.dict(os.environ, env_var, clear=True):
            settings = Settings()
            assert settings.debug_save_frames is True
    
    env_vars_false = [
        {"DEBUG_SAVE_FRAMES": "false"},
        {"DEBUG_SAVE_FRAMES": "False"},
        {"DEBUG_SAVE_FRAMES": "0"},
        {"DEBUG_SAVE_FRAMES": "no"},
        {},
    ]
    
    for env_var in env_vars_false:
        with patch.dict(os.environ, env_var, clear=True):
            settings = Settings()
            assert settings.debug_save_frames is False


# ----------------------------
# Tests de output_dir
# ----------------------------
def test_output_dir_normalization():
    """Relative output_dir stays relative; ``~`` is expanded (typically absolute under the user home)."""
    settings = Settings(output_dir="test_output")
    assert settings.output_dir == "test_output"
    assert not Path(settings.output_dir).is_absolute()

    settings = Settings(output_dir="~/test_output")
    assert "~" not in settings.output_dir
    assert Path(settings.output_dir).expanduser() == Path(settings.output_dir)


def test_output_dir_strips_and_default_output():
    with patch.dict(os.environ, {}, clear=True):
        assert Settings(output_dir="  my_out/ ").output_dir == "my_out"
        assert Settings(output_dir="").output_dir == "output"
        assert Settings(output_dir="   ").output_dir == "output"


def test_ensure_output_dir():
    """Test que ensure_output_dir crea el directorio si no existe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "new_output_dir"
        settings = Settings(output_dir=str(output_path))
        
        # El directorio no debería existir inicialmente
        assert not output_path.exists()
        
        # Crear el directorio
        created_path = settings.ensure_output_dir()
        
        # Verificar que se creó
        assert output_path.exists()
        assert output_path.is_dir()
        # Comparar paths resueltos para evitar problemas con symlinks
        assert created_path.resolve() == output_path.resolve()


def test_ensure_output_dir_existing():
    """Test que ensure_output_dir no falla si el directorio ya existe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(output_dir=tmpdir)
        
        # El directorio ya existe
        assert Path(tmpdir).exists()
        
        # No debería fallar
        created_path = settings.ensure_output_dir()
        # Comparar paths resueltos para evitar problemas con symlinks
        assert created_path.resolve() == Path(tmpdir).resolve()


# ----------------------------
# Tests de funciones de carga
# ----------------------------
def test_load_settings():
    """Test de la función load_settings."""
    with patch.dict(os.environ, {}, clear=True):
        settings1 = load_settings()
        settings2 = load_settings()
        
        # Debería retornar la misma instancia (cached)
        assert settings1 is settings2


def test_reload_settings():
    """Test de la función reload_settings."""
    # Limpiar la instancia global primero
    import src.config
    src.config._settings = None
    
    # Cargar configuración inicial
    settings1 = load_settings()
    initial_fps = settings1.extract_fps
    
    # Recargar configuración (debería crear nueva instancia)
    settings2 = reload_settings()
    
    # Debería ser una nueva instancia
    assert settings2 is not settings1
    # Debería tener los mismos valores (mismo entorno)
    assert settings2.extract_fps == initial_fps
    
    # Limpiar para otros tests
    src.config._settings = None


def test_get_settings():
    """Test de la función get_settings."""
    with patch.dict(os.environ, {}, clear=True):
        settings = get_settings()
        assert isinstance(settings, Settings)


# ----------------------------
# Tests de API key
# ----------------------------
def test_api_key_empty_allowed():
    """Test que API key vacía es permitida (validación se hace al usar)."""
    settings = Settings(gemini_api_key="")
    assert settings.gemini_api_key == ""


def test_api_key_from_env():
    """Test que API key se carga desde variable de entorno."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key_123"}, clear=True):
        settings = Settings()
        assert settings.gemini_api_key == "test_key_123"


# ----------------------------
# Tests de modelo de Gemini
# ----------------------------
def test_gemini_model_name_default():
    """Test del valor por defecto del modelo."""
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings()
        assert settings.gemini_model_name == "gemini-2.0-flash-exp"


def test_gemini_model_name_from_env():
    """Test que el modelo se carga desde variable de entorno."""
    with patch.dict(os.environ, {"GEMINI_MODEL_NAME": "gemini-pro"}, clear=True):
        settings = Settings()
        assert settings.gemini_model_name == "gemini-pro"


# ----------------------------
# Tests de extra="forbid"
# ----------------------------
def test_extra_fields_forbidden():
    """Test que no se permiten campos extra."""
    with pytest.raises(Exception):  # ValidationError de Pydantic
        Settings(extra_field="not_allowed")
