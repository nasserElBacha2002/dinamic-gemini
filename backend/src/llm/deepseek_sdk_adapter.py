"""
DeepSeek — Phase 9 provider using **Option A (OpenAI-compatible API)**.

DeepSeek exposes a Chat Completions–compatible HTTPS API. We use the official ``openai`` Python
client with ``base_url`` pointing at DeepSeek and ``DEEPSEEK_API_KEY`` for auth.

**Multimodal (images):** The hosted ``api.deepseek.com`` Chat Completions API does not accept
OpenAI-style ``image_url`` message parts. Hybrid warehouse analysis always attaches images, so
``DeepSeekSdkAdapter.execute`` rejects requests that include frames or context images with
``LLMProviderError`` code ``UNSUPPORTED_MULTIMODAL_PROVIDER`` before any HTTP call. Text-only
requests (no frames, no context images) still delegate to ``OpenAiSdkAdapter``.

**Architectural boundaries:**
- Logical provider key and ``LLMResponse.provider`` are always ``deepseek`` (never ``openai``).
- Job/request metadata uses ``deepseek_model_name`` only — never ``openai_model_name``.
- Prompt composition uses the hybrid **default** branch (same as Gemini/Claude), not the OpenAI
  overlay; see ``hybrid_resolution``.

If DeepSeek diverges from OpenAI-compatible behavior in the future, introduce Option B
(``DeepSeekSdkAdapter`` with a native HTTP client) without reusing this file’s assumptions.
"""

from __future__ import annotations

import logging
from typing import Any

from src.llm.errors import LLMProviderError
from src.llm.openai_sdk_adapter import OpenAiCompatibleVendorConfig, OpenAiSdkAdapter
from src.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

_DEEPSEEK_VENDOR = OpenAiCompatibleVendorConfig(
    logical_provider="deepseek",
    settings_api_key_attr="deepseek_api_key",
    settings_model_attr="deepseek_model",
    settings_timeout_attr="deepseek_request_timeout_sec",
    settings_max_side_attr="deepseek_vision_max_image_side",
    model_metadata_key="deepseek_model_name",
    hybrid_compose_provider_key="deepseek",
    missing_api_key_user_message="DEEPSEEK_API_KEY not set",
    default_model_if_settings_empty="deepseek-chat",
    raw_response_filename="deepseek_raw_response.json",
    log_label="DeepSeek",
    settings_base_url_attr="deepseek_api_base_url",
    default_base_url="https://api.deepseek.com",
)


def _deepseek_request_includes_images(request: LLMRequest) -> bool:
    if request.context_images:
        return True
    if request.frames_nd and len(request.frames_nd) > 0:
        return True
    if request.frames and len(request.frames) > 0:
        return True
    return False


class DeepSeekSdkAdapter(OpenAiSdkAdapter):
    """DeepSeek vendor config; blocks multimodal requests before ``OpenAiSdkAdapter`` HTTP calls."""

    def __init__(self) -> None:
        super().__init__(vendor_config=_DEEPSEEK_VENDOR)

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        v = _DEEPSEEK_VENDOR
        if _deepseek_request_includes_images(request):
            meta = request.metadata or {}
            job_model = (meta.get(v.model_metadata_key) or "").strip()
            default_m = (
                getattr(settings, v.settings_model_attr, "") or v.default_model_if_settings_empty
            )
            default_m = str(default_m).strip() if default_m is not None else ""
            effective_model = job_model or default_m or "(unset)"
            logger.warning(
                "[DeepSeek] Skipped provider execution: unsupported multimodal input (images present) "
                "(model=%s, job_id=%s)",
                effective_model,
                request.job_id,
            )
            raise LLMProviderError(
                code="UNSUPPORTED_MULTIMODAL_PROVIDER",
                message="DeepSeek is not currently supported for image-based analysis jobs.",
                details={
                    "provider": v.logical_provider,
                    "reason": "DeepSeek API does not support multimodal input in current integration",
                    "model": effective_model,
                    "job_id": request.job_id,
                },
            )
        return super().execute(request, settings)
