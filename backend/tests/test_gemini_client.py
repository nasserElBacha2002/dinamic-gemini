"""
Tests unitarios para el cliente de Gemini (flujo híbrido único).

Verifica:
- Inicialización del cliente
- generate_global_analysis_raw y generate_global_analysis_structured
- Manejo de errores y retry
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.llm.gemini_client import GeminiClient
from src.llm.prompts import get_hybrid_prompt, GLOBAL_ENTITY_ANALYSIS_PROMPT_V21, HYBRID_PROMPTS


# ----------------------------
# Tests de inicialización
# ----------------------------
def test_gemini_client_init_success():
    """Test de inicialización exitosa del cliente."""
    with patch("src.llm.gemini_client.genai.Client", return_value=MagicMock()):
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
    with patch("src.llm.gemini_client.genai.Client", return_value=MagicMock()):
        client = GeminiClient(api_key="test_key", model_name="gemini-pro")
        assert client.model_name == "gemini-pro"


# ----------------------------
# Tests de generate_global_analysis_raw
# ----------------------------
def test_generate_global_analysis_raw_success():
    """Test de llamada raw exitosa."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"count": 5}'
    mock_client.models.generate_content.return_value = mock_response

    with patch("src.llm.gemini_client.genai.Client", return_value=mock_client):
        client = GeminiClient(api_key="test_key")
        images = [MagicMock()]
        result = client.generate_global_analysis_raw(images, "Count boxes")
        assert result == '{"count": 5}'


def test_generate_global_analysis_raw_empty_images():
    """Test que se lanza error si images está vacía."""
    with patch("src.llm.gemini_client.genai.Client", return_value=MagicMock()):
        client = GeminiClient(api_key="test_key")
        with pytest.raises(ValueError, match="no puede estar vacía"):
            client.generate_global_analysis_raw([], "prompt")


# ----------------------------
# Tests de generate_global_analysis_structured
# ----------------------------
def test_generate_global_analysis_structured_success():
    """Test de llamada structured exitosa."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"total_entities_detected": 1, "entities": []}'
    mock_client.models.generate_content.return_value = mock_response

    with patch("src.llm.gemini_client.genai.Client", return_value=mock_client):
        client = GeminiClient(api_key="test_key")
        images = [MagicMock()]
        from src.models.schemas import GlobalEntityResponseV21
        result = client.generate_global_analysis_structured(
            images, "Analyze", GlobalEntityResponseV21
        )
        assert "total_entities_detected" in result


def test_generate_global_analysis_structured_empty_images():
    """Test que se lanza error si images está vacía."""
    with patch("src.llm.gemini_client.genai.Client", return_value=MagicMock()):
        client = GeminiClient(api_key="test_key")
        from src.models.schemas import GlobalEntityResponseV21
        with pytest.raises(ValueError, match="no puede estar vacía"):
            client.generate_global_analysis_structured([], "prompt", GlobalEntityResponseV21)


# ----------------------------
# Tests de prompts (get_hybrid_prompt)
# ----------------------------
def test_get_hybrid_prompt_default():
    """Test que get_hybrid_prompt devuelve el prompt global_v21 por defecto."""
    text = get_hybrid_prompt("global_v21")
    assert text == GLOBAL_ENTITY_ANALYSIS_PROMPT_V21
    assert "PALLET" in text
    assert "entity" in text


def test_get_hybrid_prompt_unknown_falls_back():
    """Test que perfil desconocido devuelve global_v21."""
    text = get_hybrid_prompt("unknown_profile")
    assert text == GLOBAL_ENTITY_ANALYSIS_PROMPT_V21


def test_hybrid_prompts_registry():
    """Test que el registro tiene al menos global_v21."""
    assert "global_v21" in HYBRID_PROMPTS
    assert HYBRID_PROMPTS["global_v21"] == GLOBAL_ENTITY_ANALYSIS_PROMPT_V21
