"""
Cliente para integración con Gemini API.

Responsabilidades:
- Construir requests a Gemini API
- Enviar frames individualmente
- Parsear respuestas JSON
- Manejar errores y reintentos
- Implementar retry con "repair JSON"
"""

import json
import time
from pathlib import Path
from typing import List, Optional

import google.genai as genai
from google.genai import types
from pydantic import TypeAdapter, ValidationError

from src.models.schemas import (
    FrameRef,
    LLMFrameResult,
    LLMPalletObservation,
    LLMProductObservation,
    MinifiedFrameResult,
)
from src.llm.prompts import get_prompt_profile


# Nota: _expand_json_schema ya no es necesario con el nuevo SDK
# El nuevo SDK acepta clases Pydantic directamente sin necesidad de limpiar el schema


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

    def _load_image(self, image_path: str):
        """Carga una imagen desde un archivo.
        
        Args:
            image_path: Ruta al archivo de imagen.
        
        Returns:
            Objeto de imagen compatible con Gemini API.
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImportError(
                "Pillow no está instalado. Instálalo con: pip install pillow"
            )
        
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Imagen no encontrada: {image_path}")
        
        return Image.open(path)

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
                    types_list = [t.get("type") for t in obj["anyOf"] if isinstance(t, dict) and "type" in t]
                    if "null" in types_list:
                        types_list.remove("null")
                        obj["nullable"] = True
                    if types_list:
                        obj["type"] = types_list[0]
                    del obj["anyOf"]
                    
                return {k: clean_node(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_node(item) for item in obj]
            return obj
            
        return clean_node(schema)

    def _analyze_single_frame(
        self,
        frame: FrameRef,
        image_path: str,
        prompt_profile: str = "pallet_count_simple",
    ) -> LLMFrameResult:
        """Analiza un solo frame usando Structured Outputs de Gemini.
        
        Con response_mime_type="application/json" y response_schema, Gemini siempre
        devuelve JSON válido, eliminando la necesidad de limpieza o repair loops.
        
        Args:
            frame: Referencia al frame.
            image_path: Ruta a la imagen del frame.
            prompt_profile: Perfil de prompt a usar.
        
        Returns:
            LLMFrameResult con los resultados del análisis.
        """
        profile = get_prompt_profile(prompt_profile)
        
        # Cargar imagen
        try:
            image = self._load_image(image_path)
        except Exception as e:
            return LLMFrameResult(
                frame=frame,
                pallets=[],
                raw_text=f"ERROR: {e}",
                model_name=self.model_name,
            )
        
        # Obtenemos el esquema 100% compatible con Gemini (limpio de anyOf, title, etc.)
        safe_schema = self._get_safe_schema(MinifiedFrameResult)
        
        # Configuración de generación con Structured Outputs
        generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=safe_schema,  # Schema limpio compatible con Gemini
            temperature=0.0,  # Temperatura 0.0 para conteo matemático exacto
            system_instruction=profile["system"],  # System prompt en la configuración
            safety_settings=self.safety_settings,  # Safety settings dentro del config
        )
        
        last_error = None
        
        # Reintentos solo para errores de red/API (429, 503, etc.)
        for attempt in range(self.max_retries):
            try:
                # ¡Magia pura! Pasamos la imagen de Pillow directamente - el nuevo SDK lo acepta
                contents = [image, profile["user"]]
                
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=generation_config,
                )
                
                raw_text = response.text
                
                # Parseo directo y validación estricta con Pydantic.
                # No se necesita limpiar Markdown porque la API devuelve JSON puro.
                minified_data = TypeAdapter(MinifiedFrameResult).validate_json(raw_text)
                
                # Mapeo a modelos internos
                llm_pallet_observations = []
                for m_pallet in minified_data.pallets:
                    llm_products = [
                        LLMProductObservation(
                            brand=m_prod.b,
                            product=m_prod.n,
                            estimated_boxes=m_prod.q,
                            confidence=m_prod.c,
                            reasoning=m_prod.r,  # Incluir razonamiento matemático
                        )
                        for m_prod in m_pallet.p
                    ]
                    llm_pallet_observations.append(
                        LLMPalletObservation(pallet_id=m_pallet.id, products=llm_products)
                    )
                
                return LLMFrameResult(
                    frame=frame,
                    pallets=llm_pallet_observations,
                    raw_text=raw_text,
                    model_name=self.model_name,
                )
                
            except Exception as e:
                last_error = str(e)
                # Si es error de validación (Pydantic), la API falló en el contrato interno,
                # pero es raro con Structured Outputs.
                # Normalmente los errores aquí serán 429 (Rate Limit) o 503 (Service Unavailable)
                if "429" in str(e) or "rate limit" in str(e).lower():
                    wait_time = self.retry_delay * (2 ** attempt)
                    time.sleep(wait_time)
                else:
                    time.sleep(self.retry_delay)
        
        # Si fallaron todos los intentos de red/API
        return LLMFrameResult(
            frame=frame,
            pallets=[],
            raw_text=f"ERROR crítico tras {self.max_retries} intentos: {last_error}",
            model_name=self.model_name,
        )

    def analyze_frames(
        self,
        frames: List[FrameRef],
        image_paths: List[str],
        prompt_profile: str = "multi_frame_consolidated",
    ) -> List[LLMFrameResult]:
        """Analiza múltiples frames en una sola llamada a Gemini para evitar duplicados.
        
        Envía todas las imágenes en una sola llamada para que Gemini consolide
        los resultados y evite duplicar pallets que aparecen en múltiples frames.
        
        Args:
            frames: Lista de referencias a frames.
            image_paths: Lista de rutas a las imágenes correspondientes.
            prompt_profile: Perfil de prompt a usar (default: "multi_frame_consolidated").
        
        Returns:
            Lista con un solo LLMFrameResult consolidado.
        
        Raises:
            ValueError: Si las listas de frames e image_paths no tienen la misma longitud.
        """
        if len(frames) != len(image_paths):
            raise ValueError(
                f"frames e image_paths deben tener la misma longitud: "
                f"{len(frames)} frames vs {len(image_paths)} paths"
            )
        
        if not frames:
            return []
        
        print(f"  Enviando {len(frames)} frames en una sola llamada a Gemini...")
        
        # Usar el primer frame como referencia para el resultado
        reference_frame = frames[0]
        
        # Cargar todas las imágenes
        images = []
        for image_path in image_paths:
            try:
                image = self._load_image(image_path)
                images.append(image)
            except Exception as e:
                print(f"  ⚠️  Error cargando imagen {image_path}: {e}")
                continue
        
        if not images:
            return [
                LLMFrameResult(
                    frame=reference_frame,
                    pallets=[],
                    raw_text="ERROR: No se pudieron cargar las imágenes",
                    model_name=self.model_name,
                )
            ]
        
        # Obtener prompts del perfil
        profile = get_prompt_profile(prompt_profile)
        
        # Obtenemos el esquema 100% compatible con Gemini (limpio de anyOf, title, etc.)
        safe_schema = self._get_safe_schema(MinifiedFrameResult)
        
        # Configuración de generación con Structured Outputs
        generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=safe_schema,  # Schema limpio compatible con Gemini
            temperature=0.0,
            system_instruction=profile["system"],
            safety_settings=self.safety_settings,  # Safety settings dentro del config
        )
        
        last_error = None
        
        # Reintentos solo para errores de red/API
        for attempt in range(self.max_retries):
            try:
                # ¡Magia pura! Pasamos la lista de imágenes (objetos PIL) directamente
                contents = images + [profile["user"]]
                
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=generation_config,
                )
                
                raw_text = response.text
                
                # Parseo directo y validación estricta con Pydantic
                minified_data = TypeAdapter(MinifiedFrameResult).validate_json(raw_text)
                
                # Mapeo a modelos internos
                llm_pallet_observations = []
                for m_pallet in minified_data.pallets:
                    llm_products = [
                        LLMProductObservation(
                            brand=m_prod.b,
                            product=m_prod.n,
                            estimated_boxes=m_prod.q,
                            confidence=m_prod.c,
                            reasoning=m_prod.r,  # Incluir razonamiento matemático
                        )
                        for m_prod in m_pallet.p
                    ]
                    llm_pallet_observations.append(
                        LLMPalletObservation(pallet_id=m_pallet.id, products=llm_products)
                    )
                
                # Retornar un solo resultado consolidado
                return [
                    LLMFrameResult(
                        frame=reference_frame,
                        pallets=llm_pallet_observations,
                        raw_text=raw_text,
                        model_name=self.model_name,
                    )
                ]
                
            except Exception as e:
                last_error = str(e)
                if "429" in str(e) or "rate limit" in str(e).lower():
                    wait_time = self.retry_delay * (2 ** attempt)
                    time.sleep(wait_time)
                else:
                    time.sleep(self.retry_delay)
        
        # Si fallaron todos los intentos
        return [
            LLMFrameResult(
                frame=reference_frame,
                pallets=[],
                raw_text=f"ERROR crítico tras {self.max_retries} intentos: {last_error}",
                model_name=self.model_name,
            )
        ]
