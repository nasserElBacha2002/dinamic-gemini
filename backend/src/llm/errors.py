"""Stage 2.2.D — LLM provider errors."""

from typing import Any, Dict, Optional


class LLMProviderError(Exception):
    """Raised when an LLM provider fails (config, network, parse, schema)."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.details = dict(details) if details else {}
        super().__init__(f"[{code}] {message}")
