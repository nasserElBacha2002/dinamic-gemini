"""Phase 1 follow-up — Gemini adapter/analyzer interleaved contents."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer
from src.llm.vision_multimodal_payload import ROLE_PRIMARY_EVIDENCE, ROLE_REFERENCE_ONLY


def test_gemini_analyzer_passes_interleaved_contents_to_client() -> None:
    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = (
        '{"total_entities_detected": 0, "entities": []}'
    )
    analyzer = GeminiGlobalAnalyzer(mock_client, prompt_text="Main rules here.")
    frame = np.zeros((12, 12, 3), dtype=np.uint8)
    ref_pil = MagicMock()

    analyzer.analyze_video_frames(
        [frame],
        context_images=[ref_pil],
        frame_refs=["img_010"],
        reference_image_ids=["ref-9"],
        request_metadata={},
    )

    contents = mock_client.generate_global_analysis_structured.call_args.kwargs["contents"]

    assert isinstance(contents[0], str)
    assert "Main rules here" in contents[0]
    assert ROLE_REFERENCE_ONLY in contents[1]
    assert "ref-9" in contents[1]
    assert contents[2] is ref_pil
    assert ROLE_PRIMARY_EVIDENCE in contents[3]
    assert "img_010" in contents[3]
    assert not isinstance(contents[-1], str) or "Main rules here" not in contents[-1]
