"""Stage 2.2.D — Gemini LLM provider (wraps existing client + analyzer)."""

import logging
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
from src.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class GeminiProvider:
    """LLM provider that uses Gemini (same prompt/schema/retry as before).

    Note: request.prompt and request.schema_version are currently ignored. The
    underlying GeminiGlobalAnalyzer uses its own prompt and v2.1 schema; wiring
    request.prompt/schema_version into the analyzer is left for a future change.
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
        client = GeminiClient(
            api_key=self._settings.gemini_api_key,
            model_name=getattr(self._settings, "gemini_model_name", "gemini-2.0-flash-exp"),
            max_retries=getattr(self._settings, "gemini_max_retries", 3),
            retry_delay=getattr(self._settings, "gemini_retry_delay", 1.0),
        )
        analyzer = GeminiGlobalAnalyzer(client)
        try:
            data = analyzer.analyze_video_frames(frames_nd, logger=logger)
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
