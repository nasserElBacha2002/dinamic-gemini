"""
Cliente para integración con Gemini API (flujo híbrido único).

Responsabilidades:
- Construir requests a Gemini API (análisis global raw o structured)
- Manejar errores y reintentos
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import google.genai as genai
from google.genai import types


class GeminiClient:
    """Cliente para interactuar con la API de Gemini."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash-exp",
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """Inicializa el cliente de Gemini.
        
        Args:
            api_key: API key de Gemini.
            model_name: Nombre del modelo a usar.
            max_retries: Número máximo de reintentos.
            retry_delay: Delay inicial entre reintentos (segundos).
        
        Raises:
            RuntimeError: Si la API key está vacía.
        """
        if not api_key:
            raise RuntimeError("Falta GEMINI_API_KEY. Configúrala en .env o como variable de entorno.")
        
        self.api_key = api_key
        self.model_name = model_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.last_response_usage: Dict[str, Any] = {}
        
        # Inicializar cliente con el nuevo SDK
        self.client = genai.Client(api_key=api_key)
        
        # Configuración de seguridad (nuevo SDK format - lista de objetos SafetySetting)
        self.safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
        ]

    def _extract_usage(self, response: Any) -> Dict[str, Any]:
        """Best-effort usage extraction across Gemini SDK response variants."""
        usage: Dict[str, Any] = {}
        meta = getattr(response, "usage_metadata", None) or getattr(response, "usageMetadata", None)
        if meta is not None:
            candidates = {
                "prompt_token_count": getattr(meta, "prompt_token_count", None)
                or getattr(meta, "promptTokenCount", None),
                "candidates_token_count": getattr(meta, "candidates_token_count", None)
                or getattr(meta, "candidatesTokenCount", None),
                "total_token_count": getattr(meta, "total_token_count", None)
                or getattr(meta, "totalTokenCount", None),
                "thoughts_token_count": getattr(meta, "thoughts_token_count", None)
                or getattr(meta, "thoughtsTokenCount", None),
                "cached_content_token_count": getattr(meta, "cached_content_token_count", None)
                or getattr(meta, "cachedContentTokenCount", None),
            }
            usage.update({k: v for k, v in candidates.items() if v is not None})
        if not usage and isinstance(response, dict):
            md = response.get("usage_metadata") or response.get("usageMetadata") or {}
            if isinstance(md, dict):
                for key in (
                    "prompt_token_count",
                    "candidates_token_count",
                    "total_token_count",
                    "thoughts_token_count",
                    "cached_content_token_count",
                ):
                    if md.get(key) is not None:
                        usage[key] = md.get(key)
        return usage

    def _get_safe_schema(self, model_class) -> dict:
        """Limpia el esquema de Pydantic para que Gemini no tire error 400.
        
        Elimina campos que Gemini rechaza: anyOf, title, additionalProperties, etc.
        
        Args:
            model_class: Clase Pydantic de la cual obtener el schema.
        
        Returns:
            Schema JSON limpio compatible con Gemini.
        """
        schema = model_class.model_json_schema()
        defs = schema.pop("$defs", {})
        
        def clean_node(obj):
            """Recursivamente limpia el schema."""
            if isinstance(obj, dict):
                # Borramos basura que Gemini no soporta
                obj.pop("title", None)
                obj.pop("default", None)
                obj.pop("additionalProperties", None)
                
                # Resolvemos referencias
                if "$ref" in obj:
                    ref_name = obj["$ref"].split("/")[-1]
                    if ref_name in defs:
                        return clean_node(defs[ref_name].copy())
                
                # Arreglamos los Optional (anyOf -> nullable)
                if "anyOf" in obj:
                    variants = [t for t in obj["anyOf"] if isinstance(t, dict)]
                    non_null = [v for v in variants if v.get("type") != "null"]
                    if len(variants) != len(non_null):
                        obj["nullable"] = True
                    if non_null:
                        chosen = non_null[0]
                        obj["type"] = chosen.get("type")
                        # Preservar "items" para arrays (Gemini lo exige)
                        if chosen.get("type") == "array" and "items" in chosen:
                            obj["items"] = clean_node(chosen["items"].copy())
                    del obj["anyOf"]
                    
                return {k: clean_node(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_node(item) for item in obj]
            return obj
            
        return clean_node(schema)

    def generate_global_analysis_raw(
        self,
        images: List,
        prompt: str,
    ) -> str:
        """Una llamada a Gemini con varias imágenes y un prompt; devuelve JSON en crudo (v2.0 hybrid).

        No usa response_schema; la respuesta debe ser JSON válido según el prompt.

        Args:
            images: Lista de imágenes PIL (o compatibles con el SDK).
            prompt: Prompt de usuario (texto).

        Returns:
            response.text (string JSON).

        Raises:
            RuntimeError: Si fallan todos los reintentos.
        """
        if not images:
            raise ValueError("images no puede estar vacía")
        generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            safety_settings=self.safety_settings,
        )
        contents = list(images) + [prompt]
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=generation_config,
                )
                self.last_response_usage = self._extract_usage(response)
                return response.text or "{}"
            except Exception as e:
                last_error = str(e)
                if "429" in str(e) or "rate limit" in str(e).lower():
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    time.sleep(self.retry_delay)
        raise RuntimeError(
            f"generate_global_analysis_raw falló tras {self.max_retries} intentos: {last_error}"
        )

    def generate_global_analysis_structured(
        self,
        images: List,
        prompt: str,
        response_schema_model: type,
    ) -> str:
        """Una llamada a Gemini con structured output (response_schema). Más barata y JSON garantizado.

        Usa response_mime_type="application/json" y response_schema para que Gemini devuelva
        siempre JSON válido según el schema, reduciendo tokens del prompt y coste.

        Args:
            images: Lista de imágenes PIL (o compatibles con el SDK).
            prompt: Prompt de usuario (solo instrucciones; el schema va en la API).
            response_schema_model: Clase Pydantic del objeto raíz (ej. GlobalEntityResponseV21).

        Returns:
            response.text (string JSON que cumple el schema).
        """
        if not images:
            raise ValueError("images no puede estar vacía")
        safe_schema = self._get_safe_schema(response_schema_model)
        generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=safe_schema,
            temperature=0.0,
            safety_settings=self.safety_settings,
        )
        contents = list(images) + [prompt]
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=generation_config,
                )
                self.last_response_usage = self._extract_usage(response)
                return response.text or "{}"
            except Exception as e:
                last_error = str(e)
                if "429" in str(e) or "rate limit" in str(e).lower():
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    time.sleep(self.retry_delay)
        raise RuntimeError(
            f"generate_global_analysis_structured falló tras {self.max_retries} intentos: {last_error}"
        )
