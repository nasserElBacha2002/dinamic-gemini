"""Stage 2.2.D — LLM provider errors."""

from __future__ import annotations

from typing import Any

from src.llm.provider_error_taxonomy import (
    canonical_provider_error_code,
    provider_error_retryable,
)


class LLMProviderError(Exception):
    """Raised when an LLM provider fails (config, network, parse, schema)."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        canonical_code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = dict(details) if details else {}
        provider_key = self.details.get("provider")
        provider_key_str = str(provider_key).strip().lower() if provider_key else None
        details_retryable = self.details.get("retryable_class")
        details_retryable_bool = (
            bool(details_retryable) if isinstance(details_retryable, bool) else None
        )
        self.canonical_code = canonical_code or canonical_provider_error_code(code)
        self.retryable = (
            retryable
            if retryable is not None
            else provider_error_retryable(
                code,
                provider_key=provider_key_str,
                details_retryable_class=details_retryable_bool,
            )
        )
        if self.code != self.canonical_code:
            self.details.setdefault("legacy_code", self.code)
        legacy_suffix = (
            f" legacy_code={self.code}" if self.code != self.canonical_code else ""
        )
        super().__init__(f"[{self.canonical_code}] {message}{legacy_suffix}")
