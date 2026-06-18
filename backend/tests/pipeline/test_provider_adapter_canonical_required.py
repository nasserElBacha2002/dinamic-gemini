"""Phase 4.4 corrections — adapter canonical payload requirement."""

from __future__ import annotations

import numpy as np
import pytest

from src.llm.anthropic_sdk_adapter import _anthropic_build_message_content
from src.llm.errors import LLMProviderError
from src.llm.openai_sdk_adapter import _OPENAI_VENDOR, _openai_build_user_content
from src.llm.types import LLMRequest
from src.pipeline.services.provider_execution_errors import PROVIDER_IMAGE_MANIFEST_MISMATCH


def _canonical_required_request() -> LLMRequest:
    return LLMRequest(
        job_id="job-1",
        frames=[],
        frame_refs=["asset-1"],
        prompt="p",
        schema_version="v2.1",
        metadata={"prompt_composition": {"execution_image_manifest": {"version": 1}}},
        frames_nd=[np.zeros((2, 2, 3))],
        canonical_provider_payload_required=True,
    )


def test_openai_photo_without_provider_request_fails() -> None:
    req = _canonical_required_request()
    with pytest.raises(LLMProviderError) as exc:
        _openai_build_user_content(req, object(), _OPENAI_VENDOR, list(req.frames_nd), 512)
    assert exc.value.code == PROVIDER_IMAGE_MANIFEST_MISMATCH


def test_anthropic_photo_without_provider_request_fails() -> None:
    req = _canonical_required_request()
    with pytest.raises(LLMProviderError) as exc:
        _anthropic_build_message_content(req, object(), list(req.frames_nd), 512, effective_model="m")
    assert exc.value.code == PROVIDER_IMAGE_MANIFEST_MISMATCH


def test_gemini_photo_without_provider_request_fails() -> None:
    from src.llm.vision_multimodal_payload import resolve_serialized_payload_for_adapter
    from src.pipeline.services.provider_execution_errors import ProviderImageExecutionError

    req = _canonical_required_request()
    with pytest.raises(ProviderImageExecutionError) as exc:
        resolve_serialized_payload_for_adapter(req, provider="gemini")
    assert exc.value.code == PROVIDER_IMAGE_MANIFEST_MISMATCH
