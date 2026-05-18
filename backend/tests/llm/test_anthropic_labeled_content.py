"""Phase 1 follow-up — Claude labeled message content and multimodal_order metadata."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from src.llm.anthropic_sdk_adapter import _anthropic_build_message_content
from src.llm.types import LLMRequest
from src.llm.vision_multimodal_payload import (
    LLM_METADATA_KEY_MULTIMODAL_ORDER,
    ROLE_PRIMARY_EVIDENCE,
    ROLE_REFERENCE_ONLY,
)


def test_anthropic_build_message_content_labels_and_multimodal_order() -> None:
    pil = MagicMock()
    pil.mode = "RGB"
    pil.size = (8, 8)
    frames_nd = [np.zeros((8, 8, 3), dtype=np.uint8)]
    request = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=["img_007"],
        prompt="Task prompt.",
        schema_version="v2.1",
        metadata={"reference_image_ids": ["ref-x"]},
        frames_nd=frames_nd,
        context_images=[pil],
    )
    settings = MagicMock()

    content = _anthropic_build_message_content(
        request,
        settings,
        frames_nd,
        max_side=512,
        effective_model="claude-test",
    )

    texts = [b["text"] for b in content if b.get("type") == "text"]
    assert "Task prompt" in texts[0]
    assert any(ROLE_REFERENCE_ONLY in t and "ref-x" in t for t in texts)
    assert any(ROLE_PRIMARY_EVIDENCE in t and "img_007" in t for t in texts)
    ref_idx = next(i for i, t in enumerate(texts) if ROLE_REFERENCE_ONLY in t)
    pri_idx = next(i for i, t in enumerate(texts) if ROLE_PRIMARY_EVIDENCE in t)
    assert ref_idx < pri_idx

    order = request.metadata.get(LLM_METADATA_KEY_MULTIMODAL_ORDER)
    assert isinstance(order, list)
    assert len(order) > 0
    assert order[0]["kind"] == "main_prompt"
