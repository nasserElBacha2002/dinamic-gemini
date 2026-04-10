"""
DeepSeek — Phase 9 provider using **Option A (OpenAI-compatible API)**.

DeepSeek exposes a Chat Completions–compatible HTTPS API. We use the official ``openai`` Python
client with ``base_url`` pointing at DeepSeek and ``DEEPSEEK_API_KEY`` for auth.

**Architectural boundaries:**
- Logical provider key and ``LLMResponse.provider`` are always ``deepseek`` (never ``openai``).
- Job/request metadata uses ``deepseek_model_name`` only — never ``openai_model_name``.
- Prompt composition uses the hybrid **default** branch (same as Gemini/Claude), not the OpenAI
  overlay; see ``hybrid_resolution``.

If DeepSeek diverges from OpenAI-compatible behavior in the future, introduce Option B
(``DeepSeekSdkAdapter`` with a native HTTP client) without reusing this file’s assumptions.
"""

from __future__ import annotations

from src.llm.openai_sdk_adapter import OpenAiCompatibleVendorConfig, OpenAiSdkAdapter

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


class DeepSeekSdkAdapter(OpenAiSdkAdapter):
    """Thin adapter: same execution engine as ``OpenAiSdkAdapter``, DeepSeek vendor config."""

    def __init__(self) -> None:
        super().__init__(vendor_config=_DEEPSEEK_VENDOR)
