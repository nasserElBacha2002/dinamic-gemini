"""Opt-in live provider smoke test for Phase 5 (skipped unless credentials + flag)."""

from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_EXTERNAL_FALLBACK_LIVE_TEST", "").strip().lower()
    not in ("1", "true", "yes"),
    reason="Set RUN_EXTERNAL_FALLBACK_LIVE_TEST=true with provider credentials to run.",
)
def test_live_external_fallback_provider_smoke() -> None:
    """Controlled live call — must not run in default CI."""
    from src.application.ports.external_image_analysis_provider import (
        ExternalAnalysisContext,
        ExternalImageInput,
    )
    from src.env_settings import get_settings
    from src.infrastructure.image_processing.llm_external_image_analysis_provider import (
        LlmExternalImageAnalysisProvider,
    )

    settings = get_settings()
    provider = LlmExternalImageAnalysisProvider(
        settings=settings,
        provider_name=str(
            getattr(settings, "external_fallback_provider", "gemini") or "gemini"
        ),
        model_name=str(getattr(settings, "external_fallback_model", "") or "").strip()
        or None,
    )
    # Minimal 1x1 JPEG
    tiny_jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f"
        b"\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00"
        b"\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03"
        b"\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1"
        b"\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJ"
        b"STUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94"
        b"\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3"
        b"\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2"
        b"\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9"
        b"\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01"
        b"\x00\x00?\x00\xfb\xd5s\xff\xd9"
    )
    result = provider.analyze_image(
        ExternalImageInput(content=tiny_jpeg, asset_id="live-test"),
        ExternalAnalysisContext(
            job_id="live-test-job",
            asset_id="live-test",
            client_id=None,
            prompt_key="external_fallback_single_label",
            prompt_version="1.0.0",
            timeout_seconds=60,
            max_image_dimension=512,
            quantity_max=999,
        ),
    )
    assert result.provider_name
    assert result.status is not None
