"""Stage 2.2.D — Gemini LLM provider (wraps existing client + analyzer)."""

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.exceptions.global_analysis_exceptions import (
    GlobalAnalysisParsingError,
    GlobalAnalysisValidationError,
)
from src.llm.errors import LLMProviderError
from src.llm.gemini_client import GeminiClient
from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer
from src.llm.prompts import get_hybrid_prompt
from src.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class GeminiProvider:
    """LLM provider that uses Gemini (same prompt/schema/retry as before).

    As of Epic 3.1.A, request.prompt is used when non-empty (e.g. enriched with
    image IDs for photos jobs); otherwise falls back to get_hybrid_prompt().
    """

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "gemini"

    def analyze_global(self, request: LLMRequest) -> LLMResponse:
        if not getattr(self._settings, "gemini_api_key", ""):
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
        # Epic 3.1.A: use adapter-provided prompt when non-empty; otherwise base prompt only (no Epic D
        # product/label block — that block caused Gemini to return null for internal_code/product_label_quantity).
        use_request_prompt = (
            request.prompt.strip()
            if (request.prompt and request.prompt.strip())
            else None
        )
        prompt_text = (
            use_request_prompt
            if use_request_prompt is not None
            else get_hybrid_prompt(getattr(self._settings, "hybrid_prompt", "global_v21"))
        )
        client = GeminiClient(
            api_key=self._settings.gemini_api_key,
            model_name=getattr(self._settings, "gemini_model_name", "gemini-2.0-flash-exp"),
            max_retries=getattr(self._settings, "gemini_max_retries", 3),
            retry_delay=getattr(self._settings, "gemini_retry_delay", 1.0),
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
            model=getattr(self._settings, "gemini_model_name", None),
            latency_ms=None,
            parsed_json=data,
            raw_text=None,
            usage=None,
        )
