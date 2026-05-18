"""Phase 1 — labeled vision payloads and multimodal order metadata."""

from __future__ import annotations

import numpy as np
import pytest

from src.llm.vision_multimodal_payload import (
    PRIMARY_FRAME_REFS_MISMATCH,
    ROLE_PRIMARY_EVIDENCE,
    ROLE_REFERENCE_ONLY,
    build_anthropic_message_content_parts,
    build_gemini_interleaved_contents,
    build_openai_vision_content_parts,
    materialize_openai_content_parts,
    primary_image_label,
    reference_image_label,
    validate_primary_frame_refs,
)


def test_reference_and_primary_labels_contain_roles() -> None:
    ref = reference_image_label("sup-ref-1")
    assert ROLE_REFERENCE_ONLY in ref
    assert "sup-ref-1" in ref
    assert "source_image_id" not in ref.lower() or "do not use" in ref.lower()

    pri = primary_image_label("img_003", 2)
    assert ROLE_PRIMARY_EVIDENCE in pri
    assert "img_003" in pri
    assert "index: 2" in pri


def test_openai_content_order_main_then_labeled_pairs() -> None:
    pil = object()
    nd = np.zeros((4, 4, 3), dtype=np.uint8)
    parts, order = build_openai_vision_content_parts(
        main_prompt_text="Main prompt.",
        context_images=[pil],
        reference_image_ids=["ref-a"],
        primary_frames_nd=[nd],
        frame_refs=["img_001"],
    )
    assert parts[0]["type"] == "text"
    assert "Main prompt" in parts[0]["text"]
    assert ROLE_REFERENCE_ONLY in parts[1]["text"]
    assert parts[2]["type"] == "image_placeholder"
    assert ROLE_PRIMARY_EVIDENCE in parts[3]["text"]
    assert "img_001" in parts[3]["text"]
    assert parts[4]["type"] == "image_placeholder"
    assert order[0]["kind"] == "main_prompt"
    assert any(e["kind"] == "primary_evidence" for e in order)


def test_openai_materialize_replaces_placeholders() -> None:
    nd = np.zeros((8, 8, 3), dtype=np.uint8)
    parts, _ = build_openai_vision_content_parts(
        main_prompt_text="P",
        context_images=[],
        reference_image_ids=[],
        primary_frames_nd=[nd],
        frame_refs=["x"],
    )

    def fake_bgr(_arr: np.ndarray, _side: int) -> str:
        return "data:image/jpeg;base64,abc"

    out = materialize_openai_content_parts(
        parts,
        image_to_data_url=lambda _im, _s: "data:image/jpeg;base64,def",
        bgr_to_data_url=fake_bgr,
        max_side=512,
    )
    image_parts = [p for p in out if p.get("type") == "image_url"]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"] == "data:image/jpeg;base64,abc"


def test_gemini_contents_start_with_main_prompt_text() -> None:
    pil = object()
    contents, order = build_gemini_interleaved_contents(
        main_prompt_text="Rules and ID list here.",
        context_images=[pil],
        reference_image_ids=["ref-1"],
        primary_pil_images=[pil],
        frame_refs=["img_010"],
    )
    assert isinstance(contents[0], str)
    assert "Rules and ID list" in contents[0]
    assert ROLE_REFERENCE_ONLY in contents[1]
    assert contents[2] is pil
    assert ROLE_PRIMARY_EVIDENCE in contents[3]
    assert "img_010" in contents[3]
    assert order[0]["kind"] == "main_prompt"


def test_anthropic_content_matches_openai_label_pattern() -> None:
    nd = np.zeros((4, 4, 3), dtype=np.uint8)
    parts, order = build_anthropic_message_content_parts(
        main_prompt_text="Analyze.",
        context_images=[],
        reference_image_ids=[],
        primary_frames_nd=[nd, nd],
        frame_refs=["a", "b"],
    )
    text_parts = [p for p in parts if p.get("type") == "text"]
    assert len(text_parts) == 3  # main + 2 primary labels
    assert "source_image_id: a" in text_parts[1]["text"]
    assert "source_image_id: b" in text_parts[2]["text"]
    assert sum(1 for e in order if e["kind"] == "primary_evidence") == 2


@pytest.mark.parametrize(
    "frames,refs",
    [
        ([np.zeros((2, 2, 3))], []),
        ([np.zeros((2, 2, 3))], ["a", "b"]),
        ([], ["a"]),
        ([np.zeros((2, 2, 3))], [""]),
        ([np.zeros((2, 2, 3))], ["   "]),
    ],
)
def test_validate_primary_frame_refs_rejects_mismatch_or_empty(
    frames: list[np.ndarray], refs: list[str]
) -> None:
    with pytest.raises(ValueError, match=PRIMARY_FRAME_REFS_MISMATCH):
        validate_primary_frame_refs(frames, refs)


def test_validate_primary_frame_refs_accepts_equal_non_empty() -> None:
    validate_primary_frame_refs([np.zeros((2, 2, 3))], ["img_001"])


def test_reference_image_missing_id_still_builds_openai_payload() -> None:
    nd = np.zeros((4, 4, 3), dtype=np.uint8)
    parts, order = build_openai_vision_content_parts(
        main_prompt_text="P",
        context_images=[nd],
        reference_image_ids=[""],
        primary_frames_nd=[nd],
        frame_refs=["img_001"],
    )
    ref_labels = [p for p in parts if p.get("type") == "text" and ROLE_REFERENCE_ONLY in p["text"]]
    assert ref_labels
    assert "unknown" in ref_labels[0]["text"]
