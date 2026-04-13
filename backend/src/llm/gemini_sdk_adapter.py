"""
Gemini SDK adapter — encapsulates GeminiClient / GeminiGlobalAnalyzer (Phase 4).

Used by ``GeminiProvider`` and the pipeline provider registry. Keeps vendor types out of
pipeline strategies except through ``LLMRequest`` / ``LLMResponse``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2

from src.exceptions.global_analysis_exceptions import (
    GlobalAnalysisParsingError,
    GlobalAnalysisValidationError,
)
from src.llm.errors import LLMProviderError
from src.llm.gemini_client import GeminiClient
from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer
from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base_from_settings
from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_PARITY_MODE
from src.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class GeminiSdkAdapter:
    """Calls Gemini REST/SDK stack; maps parse/validation/network errors to ``LLMProviderError``."""

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        if not getattr(settings, "gemini_api_key", ""):
            raise LLMProviderError(
                code="NOT_CONFIGURED",
                message="GEMINI_API_KEY not set",
                details={"provider": "gemini"},
            )
        if request.frames_nd and len(request.frames_nd) > 0:
            frames_nd = list(request.frames_nd)
        else:
            frames_nd = []
            for p in request.frames:
                img = cv2.imread(str(p))
                if img is not None:
                    frames_nd.append(img)
        if not frames_nd:
            raise LLMProviderError(
                code="NO_FRAMES",
                message="No frames could be loaded",
                details={"paths_count": len(request.frames)},
            )
        meta = request.metadata or {}
        prompt_parity_mode = bool(meta.get(LLM_METADATA_KEY_PROMPT_PARITY_MODE))
        use_request_prompt = (
            request.prompt.strip()
            if (request.prompt and request.prompt.strip())
            else None
        )
        prompt_text = (
            use_request_prompt
            if use_request_prompt is not None
            else compose_hybrid_base_from_settings(
                settings, pipeline_provider_key=None, prompt_parity_mode=prompt_parity_mode
            )
        )
        effective_model = (meta.get("gemini_model_name") or "").strip() or getattr(
            settings, "gemini_model_name", "gemini-2.0-flash-exp"
        )
        client = GeminiClient(
            api_key=settings.gemini_api_key,
            model_name=str(effective_model),
            max_retries=getattr(settings, "gemini_max_retries", 3),
            retry_delay=getattr(settings, "gemini_retry_delay", 1.0),
        )
        analyzer = GeminiGlobalAnalyzer(client, prompt_text=prompt_text)
        run_dir = request.metadata.get("run_dir")
        save_raw_to_path = Path(run_dir) / "gemini_raw_response.json" if run_dir else None
        try:
            data = analyzer.analyze_video_frames(
                frames_nd,
                context_instruction=getattr(request, "context_instruction", None),
                context_images=getattr(request, "context_images", None),
                logger=logger,
                save_raw_to_path=save_raw_to_path,
            )
        except GlobalAnalysisParsingError as e:
            raise LLMProviderError(
                code="INVALID_JSON",
                message=str(e),
                details={"provider": "gemini"},
            ) from e
        except GlobalAnalysisValidationError as e:
            raise LLMProviderError(
                code="SCHEMA_INVALID",
                message=str(e),
                details={"provider": "gemini"},
            ) from e
        except RuntimeError as e:
            msg = str(e).lower()
            if "429" in str(e) or "rate limit" in msg:
                raise LLMProviderError(
                    code="RATE_LIMIT",
                    message=str(e),
                    details={"provider": "gemini"},
                ) from e
            if "timeout" in msg or "timed out" in msg:
                raise LLMProviderError(
                    code="TIMEOUT",
                    message=str(e),
                    details={"provider": "gemini"},
                ) from e
            raise LLMProviderError(
                code="UNKNOWN",
                message=str(e),
                details={"provider": "gemini"},
            ) from e
        except ValueError as e:
            raise LLMProviderError(
                code="UNKNOWN",
                message=str(e),
                details={"provider": "gemini"},
            ) from e
        return LLMResponse(
            provider="gemini",
            model=str(effective_model),
            latency_ms=None,
            parsed_json=data,
            raw_text=None,
            usage=None,
        )
