"""
Análisis global de video con una sola llamada a Gemini (hybrid v2.1, Structured Output).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

import numpy as np

from src.exceptions.global_analysis_exceptions import (
    GlobalAnalysisParsingError,
    GlobalAnalysisValidationError,
)
from src.llm.gemini_client import GeminiClient
from src.llm.prompt_composer.hybrid_assembly import (
    DEFAULT_HYBRID_PROMPT_PROFILE,
    compose_hybrid_base,
)
from src.llm.types import LLMRequest
from src.llm.vision_multimodal_payload import (
    LLM_METADATA_KEY_MULTIMODAL_ORDER,
    LLM_METADATA_KEY_REFERENCE_IMAGE_IDS,
    build_gemini_contents_from_serialized,
    build_gemini_interleaved_contents,
    resolve_serialized_payload_for_adapter,
)
from src.pipeline.services.provider_execution_errors import ProviderImageExecutionError
from src.models.schemas import GlobalEntityResponseV21
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

logger = logging.getLogger(__name__)


def _ndarray_to_pil(frame: np.ndarray):
    """Convierte frame BGR (OpenCV) a PIL Image RGB."""
    import cv2

    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow required for global analyzer. Install with: pip install pillow")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


class GeminiGlobalAnalyzer:
    """Una llamada a Gemini con todos los frames; devuelve dict JSON."""

    def __init__(self, client: GeminiClient, prompt_text: str | None = None) -> None:
        self.client = client
        self._prompt_text = prompt_text

    def analyze_video_frames(
        self,
        frames: list[np.ndarray],
        *,
        context_instruction: str | None = None,
        context_images: ContextImageSequence | None = None,
        frame_refs: list[str] | None = None,
        reference_image_ids: list[str] | None = None,
        request_metadata: dict[str, Any] | None = None,
        **kwargs: object,
    ) -> dict[str, Any]:
        """Envía los frames en una sola llamada a Gemini (Structured Output v2.1) y devuelve el JSON validado.

        Phase 1: interleaved text labels + images (main prompt first, then reference and primary pairs).
        """
        if not frames:
            raise ValueError("frames no puede estar vacía")
        run_logger = kwargs.get("logger")
        if (
            run_logger is not None
            and hasattr(run_logger, "info")
            and hasattr(run_logger, "warning")
        ):
            log = run_logger  # tests may pass MagicMock; production passes logging.Logger
        else:
            log = logger
        primary_images = [_ndarray_to_pil(f) for f in frames]
        prompt = (
            self._prompt_text
            if self._prompt_text is not None
            else compose_hybrid_base(DEFAULT_HYBRID_PROMPT_PROFILE, None)
        )
        if context_instruction and context_instruction.strip():
            prompt = context_instruction.strip() + "\n\n" + prompt

        refs = list(context_images) if context_images else []
        ref_ids = list(reference_image_ids or [])
        if request_metadata:
            raw_ref = request_metadata.get(LLM_METADATA_KEY_REFERENCE_IMAGE_IDS)
            if isinstance(raw_ref, list) and raw_ref and not ref_ids:
                ref_ids = [str(x) for x in raw_ref]
        frefs = list(frame_refs or [])

        llm_request = kwargs.get("llm_request")
        if llm_request is not None and not isinstance(llm_request, LLMRequest):
            llm_request = None

        try:
            serialized = resolve_serialized_payload_for_adapter(
                llm_request,
                provider="gemini",
            )
        except ProviderImageExecutionError:
            raise

        if serialized is not None:
            gemini_contents, multimodal_order = build_gemini_contents_from_serialized(
                main_prompt_text=prompt,
                serialized=serialized,
                job_id=getattr(llm_request, "job_id", None) if llm_request else None,
                provider="gemini",
            )
        else:
            gemini_contents, multimodal_order = build_gemini_interleaved_contents(
                main_prompt_text=prompt,
                context_images=refs,
                reference_image_ids=ref_ids,
                primary_pil_images=primary_images,
                frame_refs=frefs,
                request_metadata=request_metadata,
            )
        if request_metadata is not None:
            request_metadata[LLM_METADATA_KEY_MULTIMODAL_ORDER] = multimodal_order

        log.info(
            "Enviando Gemini interleaved contents: %d parts (%d primary frames)...",
            len(gemini_contents),
            len(frames),
        )
        raw = self.client.generate_global_analysis_structured(
            [],
            prompt,
            GlobalEntityResponseV21,
            contents=gemini_contents,
        )
        cleaned = raw.strip()
        save_raw_to_path = kwargs.get("save_raw_to_path")
        if save_raw_to_path is not None:
            p = Path(str(save_raw_to_path))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(cleaned, encoding="utf-8")
            log.info("Respuesta cruda de Gemini guardada en %s", p)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            log.warning("Global analysis parsing failed (invalid JSON): %s", e)
            raise GlobalAnalysisParsingError(f"Invalid JSON: {e}") from e
        if not isinstance(parsed, dict):
            raise GlobalAnalysisParsingError("Global analysis response must be a JSON object")

        data = parsed

        total = data.get("total_entities_detected")
        entities = data.get("entities") or []
        if (
            isinstance(entities, list)
            and isinstance(total, (int, float))
            and total != len(entities)
        ):
            log.warning(
                "Gemini count mismatch: total_entities_detected=%s vs len(entities)=%d; normalizing to len(entities)",
                total,
                len(entities),
            )
            data["total_entities_detected"] = len(entities)

        try:
            validate_global_analysis_structure_v21(data)
        except GlobalAnalysisValidationError as e:
            log.warning("Global analysis validation failed: %s", e)
            raise
        return cast(dict[str, Any], data)
