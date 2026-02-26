"""
Tests unitarios para el cliente de Gemini.

Verifica:
- Inicialización del cliente
- Parseo de respuestas JSON
- Manejo de errores
- Retry logic
- Repair JSON
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.models.schemas import FrameRef, LLMFrameResult
from src.llm.gemini_client import GeminiClient
from src.llm.prompts import get_prompt_profile


# ----------------------------
# Tests de inicialización
# ----------------------------
def test_gemini_client_init_success():
    """Test de inicialización exitosa del cliente."""
    with patch("src.llm.gemini_client.genai.configure"):
        with patch("src.llm.gemini_client.genai.GenerativeModel") as mock_model:
            client = GeminiClient(api_key="test_key_123")
            
            assert client.api_key == "test_key_123"
            assert client.model_name == "gemini-2.0-flash-exp"
            assert client.max_retries == 3


def test_gemini_client_init_no_api_key():
    """Test que se lanza error si falta API key."""
    with pytest.raises(RuntimeError, match="Falta GEMINI_API_KEY"):
        GeminiClient(api_key="")


def test_gemini_client_custom_model():
    """Test de inicialización con modelo personalizado."""
    with patch("src.llm.gemini_client.genai.configure"):
        with patch("src.llm.gemini_client.genai.GenerativeModel"):
            client = GeminiClient(api_key="test_key", model_name="gemini-pro")
            
            assert client.model_name == "gemini-pro"


# Nota: Los tests de _parse_json_response fueron eliminados porque
# ese método ya no existe. Con Structured Outputs, Gemini siempre
# devuelve JSON válido directamente.


# ----------------------------
# Tests de analyze_single_frame (mock)
# ----------------------------
def test_analyze_single_frame_success():
    """Test de análisis exitoso de un frame."""
    with patch("src.llm.gemini_client.genai.configure"):
        with patch("src.llm.gemini_client.genai.GenerativeModel") as mock_model_class:
            # Mock del modelo
            mock_model = Mock()
            mock_model_class.return_value = mock_model
            
            # Mock de la respuesta
            mock_response = Mock()
            mock_response.text = json.dumps({
                "pallets": [
                    {
                        "id": "P001",
                        "p": [{"n": "Producto", "q": 10, "c": 0.9, "b": "Marca"}],
                    }
                ]
            })
            mock_model.generate_content.return_value = mock_response
            
            client = GeminiClient(api_key="test_key")
            frame = FrameRef(frame_idx=0, timestamp_seconds=0.0)
            
            # Mock del método _load_image directamente
            mock_image = Mock()
            with patch.object(client, "_load_image", return_value=mock_image):
                result = client._analyze_single_frame(
                    frame, "/path/to/image.jpg", "pallet_count_simple"
                )
                
                assert isinstance(result, LLMFrameResult)
                assert len(result.pallets) == 1
                assert result.pallets[0].pallet_id == "P001"


def test_analyze_single_frame_image_not_found():
    """Test cuando la imagen no se encuentra."""
    with patch("src.llm.gemini_client.genai.configure"):
        with patch("src.llm.gemini_client.genai.GenerativeModel"):
            client = GeminiClient(api_key="test_key")
            frame = FrameRef(frame_idx=0, timestamp_seconds=0.0)
            
            result = client._analyze_single_frame(
                frame, "/path/that/does/not/exist.jpg", "pallet_count_simple"
            )
            
            assert isinstance(result, LLMFrameResult)
            assert len(result.pallets) == 0
            assert "ERROR" in result.raw_text


def test_analyze_single_frame_retry_on_failure():
    """Test de reintento cuando falla la API (rate limit, etc.)."""
    with patch("src.llm.gemini_client.genai.configure"):
        with patch("src.llm.gemini_client.genai.GenerativeModel") as mock_model_class:
            mock_model = Mock()
            mock_model_class.return_value = mock_model
            
            # Primera llamada: error de rate limit
            from google.api_core import exceptions
            rate_limit_error = Exception("429 Rate limit exceeded")
            
            # Segunda respuesta: JSON válido
            mock_response = Mock()
            mock_response.text = json.dumps({
                "pallets": [
                    {
                        "id": "P001",
                        "p": [{"n": "Producto", "q": 10, "c": 0.9}],
                    }
                ]
            })
            
            mock_model.generate_content.side_effect = [rate_limit_error, mock_response]
            
            client = GeminiClient(api_key="test_key", max_retries=2)
            frame = FrameRef(frame_idx=0, timestamp_seconds=0.0)
            
            # Mock del método _load_image directamente
            mock_image = Mock()
            with patch.object(client, "_load_image", return_value=mock_image):
                result = client._analyze_single_frame(
                    frame, "/path/to/image.jpg", "pallet_count_simple"
                )
                
                # Debería haber intentado 2 veces (una falló, otra exitosa)
                assert mock_model.generate_content.call_count == 2
                # Debería haber parseado exitosamente en el segundo intento
                assert len(result.pallets) == 1


# ----------------------------
# Tests de analyze_frames
# ----------------------------
def test_analyze_frames_length_mismatch():
    """Test que se lanza error si frames e image_paths no coinciden."""
    with patch("src.llm.gemini_client.genai.configure"):
        with patch("src.llm.gemini_client.genai.GenerativeModel"):
            client = GeminiClient(api_key="test_key")
            
            frames = [FrameRef(frame_idx=0, timestamp_seconds=0.0)]
            image_paths = ["path1.jpg", "path2.jpg"]
            
            with pytest.raises(ValueError, match="misma longitud"):
                client.analyze_frames(frames, image_paths)


def test_analyze_frames_empty():
    """Test con listas vacías."""
    with patch("src.llm.gemini_client.genai.configure"):
        with patch("src.llm.gemini_client.genai.GenerativeModel"):
            client = GeminiClient(api_key="test_key")
            
            results = client.analyze_frames([], [])
            
            assert len(results) == 0


def test_analyze_frames_image_load_failure_returns_error_no_api_call():
    """Bloque 6 / US-6.1: Si alguna imagen falla al cargar, no se envía request a Gemini."""
    mock_client_instance = MagicMock()
    with patch("src.llm.gemini_client.genai.Client", return_value=mock_client_instance):
        client = GeminiClient(api_key="test_key")
        frames = [
            FrameRef(frame_idx=0, timestamp_seconds=0.0),
            FrameRef(frame_idx=1, timestamp_seconds=0.1),
        ]

        def load_side_effect(path):
            if "missing" in path:
                raise FileNotFoundError(f"Imagen no encontrada: {path}")
            return MagicMock()

        with patch.object(client, "_load_image", side_effect=load_side_effect):
            results = client.analyze_frames(
                frames,
                ["/path/to/frame0.jpg", "/path/to/missing.jpg"],
            )

        assert len(results) == 1
        assert results[0].pallets == []
        assert "ERROR" in results[0].raw_text
        assert "No se pudieron cargar todas las imágenes" in results[0].raw_text
        assert "missing" in results[0].raw_text or "Imagen no encontrada" in results[0].raw_text
        # No se debe haber llamado a la API de Gemini
        mock_client_instance.models.generate_content.assert_not_called()


# ----------------------------
# Tests de prompts
# ----------------------------
def test_get_prompt_profile_valid():
    """Test de obtención de perfil válido."""
    profile = get_prompt_profile("pallet_count_simple")
    
    assert "system" in profile
    assert "user" in profile
    assert len(profile["system"]) > 0
    assert len(profile["user"]) > 0


def test_get_prompt_profile_invalid():
    """Test que se lanza error si el perfil no existe."""
    with pytest.raises(ValueError, match="no encontrado"):
        get_prompt_profile("invalid_profile")
