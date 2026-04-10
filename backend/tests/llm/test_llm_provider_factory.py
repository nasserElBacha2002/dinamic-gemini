"""Legacy ``get_llm_provider`` — Claude must use the registry executor path, not ``LLMProvider``."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.llm.providers.factory import get_llm_provider


def test_get_llm_provider_rejects_claude_with_explicit_error() -> None:
    """``llm_provider=claude`` is intentional ``ValueError``: no silent fallback to Gemini."""
    settings = MagicMock()
    settings.llm_provider = "claude"
    with pytest.raises(ValueError, match="registry"):
        get_llm_provider(settings)
