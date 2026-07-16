"""Final Anthropic content base64 validation + incident regression tests."""

from __future__ import annotations

import base64
import io
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image, ImageOps

from src.domain.execution_image_manifest import ExecutionImageRole
from src.llm.anthropic_final_image_validation import (
    measure_base64_image_dimensions,
    normalize_and_validate_anthropic_content,
)
from src.llm.anthropic_sdk_adapter import (
    AnthropicSdkAdapter,
    _anthropic_build_message_content,
    _anthropic_jpeg_content_block,
    classify_anthropic_messages_api_error,
)
from src.llm.errors import LLMProviderError
from src.llm.multimodal_image_normalization import (
    MultimodalNormalizationContext,
    ProviderImageNormalizationError,
    ProviderImagePolicy,
    normalize_multimodal_image,
    provider_image_policy_for,
)
from src.llm.provider_error_taxonomy import (
    PROVIDER_INVALID_REQUEST,
    canonical_provider_error_code,
    provider_error_retryable,
)
from src.llm.types import LLMRequest
from src.pipeline.services.provider_payload_serialization import (
    SerializedImagePayloadEntry,
    SerializedMultimodalPayload,
)


def _jpeg_bytes(w: int, h: int, *, color: tuple[int, int, int] = (40, 80, 120)) -> bytes:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _policy(max_dimension: int = 1800) -> ProviderImagePolicy:
    return provider_image_policy_for("claude", max_dimension=max_dimension, jpeg_quality=88)


def _decode_block_size(block: dict[str, Any]) -> tuple[int, int, str]:
    raw_b64 = block["source"]["data"]
    raw = base64.standard_b64decode(raw_b64)
    with Image.open(io.BytesIO(raw)) as im:
        checked = ImageOps.exif_transpose(im)
        work = checked if checked is not None else im
        return work.size[0], work.size[1], block["source"]["media_type"]


def _settings() -> SimpleNamespace:
    return SimpleNamespace(anthropic_image_jpeg_quality=88)


def _build_serialized_payload(
    primaries: list[np.ndarray],
    refs: list[Image.Image],
) -> SerializedMultimodalPayload:
    entries: list[SerializedImagePayloadEntry] = []
    pos = 0
    for i, im in enumerate(refs, start=1):
        entries.append(
            SerializedImagePayloadEntry(
                manifest_entry_id=f"man-ref-{i}",
                source_image_id=f"REF_{i:03d}",
                role=ExecutionImageRole.REFERENCE_IMAGE,
                payload_ordinal=pos,
                provider_image_position=pos,
                mime_type="image/jpeg",
                encoded_resource=im,
            )
        )
        pos += 1
    for i, nd in enumerate(primaries, start=1):
        entries.append(
            SerializedImagePayloadEntry(
                manifest_entry_id=f"man-pri-{i}",
                source_image_id=f"IMG_{i:03d}",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=pos,
                provider_image_position=pos,
                mime_type="image/jpeg",
                encoded_resource=nd,
            )
        )
        pos += 1
    return SerializedMultimodalPayload(
        entries=tuple(entries),
        provider_image_manifest_order=tuple(),
        logical_projection=tuple(),
    )


def test_final_gate_repairs_prebaked_oversized_base64_block() -> None:
    """Pre-serialized oversized JPEG must not reach the SDK unmodified."""
    oversized = _anthropic_jpeg_content_block(_jpeg_bytes(4000, 3000))
    content = [
        {"type": "text", "text": "prompt"},
        {"type": "text", "text": "label"},
        oversized,
    ]
    order = [
        {"index": 0, "role": "text", "kind": "main_prompt"},
        {"index": 1, "role": "text", "kind": "reference_image_label", "reference_id": "REF_001"},
        {
            "index": 2,
            "role": "image",
            "kind": "reference",
            "reference_id": "REF_001",
            "source_image_id": "REF_001",
        },
    ]
    w0, h0, _ = _decode_block_size(oversized)
    assert max(w0, h0) > 1800

    out, validated, meta = normalize_and_validate_anthropic_content(
        content, policy=_policy(), multimodal_order=order
    )
    w, h, media = _decode_block_size(out[2])
    assert max(w, h) <= 1800
    assert media == "image/jpeg"
    assert validated[0].was_finally_repaired is True
    assert meta[0].content_index == 2
    assert meta[0].role == "visual_reference"
    assert meta[0].reference_id == "REF_001"


def test_content_index_2_maps_first_reference_image(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    primary = [np.zeros((100, 100, 3), dtype=np.uint8)]
    ref = Image.new("RGB", (4032, 3024), (10, 20, 30))
    request = LLMRequest(
        job_id="job-map",
        frames=[],
        frame_refs=["IMG_001"],
        prompt="analyze",
        schema_version="v2.1",
        frames_nd=primary,
        context_images=[ref],
        metadata={"reference_image_ids": ["REF_001"]},
    )
    monkeypatch.setattr(
        "src.llm.anthropic_sdk_adapter.resolve_serialized_payload_for_adapter",
        lambda *a, **k: None,
    )
    content = _anthropic_build_message_content(
        request, settings, primary, 1800, effective_model="claude-test"
    )
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "text"
    assert content[2]["type"] == "image"
    w, h, media = _decode_block_size(content[2])
    assert max(w, h) <= 1800
    assert media == "image/jpeg"


def test_incident_payload_serialized_branch_all_final_le_1800(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    primaries = [np.zeros((720, 1280, 3), dtype=np.uint8) for _ in range(20)]
    refs = [
        Image.new("RGB", (4032, 3024), (10, 20, 30)),
        Image.new("RGB", (1200, 3000), (40, 50, 60)),
    ]
    serialized = _build_serialized_payload(primaries, refs)
    monkeypatch.setattr(
        "src.llm.anthropic_sdk_adapter.resolve_serialized_payload_for_adapter",
        lambda *a, **k: serialized,
    )
    request = LLMRequest(
        job_id="job-ser",
        frames=[],
        frame_refs=[f"IMG_{i:03d}" for i in range(1, 21)],
        prompt="analyze",
        schema_version="v2.1",
        frames_nd=primaries,
        context_images=refs,
        metadata={"reference_image_ids": ["REF_001", "REF_002"]},
    )
    content = _anthropic_build_message_content(
        request, settings, primaries, 1800, effective_model="claude-test"
    )
    images = [b for b in content if b.get("type") == "image"]
    assert len(images) == 22
    for block in images:
        w, h, media = _decode_block_size(block)
        assert max(w, h) <= 1800
        assert media == "image/jpeg"
        raw = base64.b64decode(block["source"]["data"], validate=True)
        assert raw[:2] == b"\xff\xd8"


def test_incident_payload_non_serialized_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    primaries = [np.zeros((720, 1280, 3), dtype=np.uint8) for _ in range(20)]
    refs = [
        Image.new("RGB", (4032, 3024), (10, 20, 30)),
        Image.new("RGB", (1200, 3000), (40, 50, 60)),
    ]
    monkeypatch.setattr(
        "src.llm.anthropic_sdk_adapter.resolve_serialized_payload_for_adapter",
        lambda *a, **k: None,
    )
    request = LLMRequest(
        job_id="job-ns",
        frames=[],
        frame_refs=[f"IMG_{i:03d}" for i in range(1, 21)],
        prompt="analyze",
        schema_version="v2.1",
        frames_nd=primaries,
        context_images=refs,
        metadata={"reference_image_ids": ["REF_001", "REF_002"]},
    )
    content = _anthropic_build_message_content(
        request, settings, primaries, 1800, effective_model="claude-test"
    )
    images = [b for b in content if b.get("type") == "image"]
    assert len(images) == 22
    assert all(max(_decode_block_size(b)[:2]) <= 1800 for b in images)


def test_fail_fast_before_messages_create(monkeypatch: pytest.MonkeyPatch) -> None:
    primaries = [np.zeros((50, 50, 3), dtype=np.uint8)]
    monkeypatch.setattr(
        "src.llm.anthropic_sdk_adapter.resolve_serialized_payload_for_adapter",
        lambda *a, **k: None,
    )

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise ProviderImageNormalizationError(
            "forced normalize failure",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
            source_id="IMG_001",
            role="primary_evidence",
        )

    monkeypatch.setattr(
        "src.llm.multimodal_image_normalization.normalize_bgr_ndarray",
        _boom,
    )
    request = LLMRequest(
        job_id="job-fail",
        frames=[],
        frame_refs=["IMG_001"],
        prompt="analyze",
        schema_version="v2.1",
        frames_nd=primaries,
        context_images=[],
        metadata={},
    )
    create = MagicMock()
    client = MagicMock()
    client.messages.create = create
    monkeypatch.setattr(
        "anthropic.Anthropic",
        lambda **kwargs: client,
    )
    adapter = AnthropicSdkAdapter()
    with pytest.raises(LLMProviderError) as ei:
        adapter.execute(
            request,
            SimpleNamespace(
                anthropic_api_key="sk-test",
                anthropic_model="claude-test",
                anthropic_request_timeout_sec=30,
                anthropic_vision_max_image_side=1800,
                anthropic_image_jpeg_quality=88,
                anthropic_max_output_tokens=1024,
                anthropic_max_retries=1,
                anthropic_retry_base_delay_sec=0.01,
            ),
        )
    assert ei.value.code == "PROVIDER_IMAGE_NORMALIZATION_FAILED"
    assert ei.value.canonical_code == PROVIDER_INVALID_REQUEST
    create.assert_not_called()


def test_single_normalize_per_image(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    primaries = [np.zeros((200, 200, 3), dtype=np.uint8) for _ in range(3)]
    refs = [Image.new("RGB", (400, 300), (1, 2, 3)) for _ in range(2)]
    monkeypatch.setattr(
        "src.llm.anthropic_sdk_adapter.resolve_serialized_payload_for_adapter",
        lambda *a, **k: None,
    )
    calls: list[str] = []
    real = normalize_multimodal_image

    def _counting(image_bytes: bytes, **kwargs: Any) -> Any:
        calls.append(str(kwargs.get("source_id")))
        return real(image_bytes, **kwargs)

    monkeypatch.setattr(
        "src.llm.multimodal_image_normalization.normalize_multimodal_image",
        _counting,
    )
    # Also patch imports already bound in encode helpers / final validation.
    monkeypatch.setattr(
        "src.llm.anthropic_final_image_validation.normalize_multimodal_image",
        _counting,
    )
    request = LLMRequest(
        job_id="job-once",
        frames=[],
        frame_refs=["IMG_001", "IMG_002", "IMG_003"],
        prompt="analyze",
        schema_version="v2.1",
        frames_nd=primaries,
        context_images=refs,
        metadata={"reference_image_ids": ["REF_001", "REF_002"]},
    )
    content = _anthropic_build_message_content(
        request, settings, primaries, 1800, effective_model="claude-test"
    )
    assert len([b for b in content if b.get("type") == "image"]) == 5
    # Materialize normalizes each image once; final gate should not re-normalize under-limit images.
    assert len(calls) == 5


def test_request_local_cache_cleared_between_builds(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr(
        "src.llm.anthropic_sdk_adapter.resolve_serialized_payload_for_adapter",
        lambda *a, **k: None,
    )
    seen_sizes: list[int] = []
    real_clear = MultimodalNormalizationContext.clear

    def _clear(self: MultimodalNormalizationContext) -> None:
        seen_sizes.append(self.size)
        real_clear(self)

    monkeypatch.setattr(MultimodalNormalizationContext, "clear", _clear)
    for color in ((1, 2, 3), (4, 5, 6)):
        primary = [np.full((80, 80, 3), color[0], dtype=np.uint8)]
        request = LLMRequest(
            job_id=f"job-{color[0]}",
            frames=[],
            frame_refs=["IMG_001"],
            prompt="analyze",
            schema_version="v2.1",
            frames_nd=primary,
            context_images=[Image.new("RGB", (60, 60), color)],
            metadata={"reference_image_ids": ["REF_001"]},
        )
        _anthropic_build_message_content(
            request, settings, primary, 1800, effective_model="claude-test"
        )
    assert len(seen_sizes) == 2
    assert all(s >= 1 for s in seen_sizes)


def test_exif_orientation_measured_after_transpose() -> None:
    img = Image.new("RGB", (200, 100), (10, 20, 30))
    exif = img.getexif()
    exif[274] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, exif=exif)
    raw = buf.getvalue()
    with Image.open(io.BytesIO(raw)) as opened:
        transposed = ImageOps.exif_transpose(opened)
        assert transposed is not None
        tw, th = transposed.size
    out = normalize_multimodal_image(
        raw, source_id="e", role="primary_evidence", policy=_policy()
    )
    assert (out.original_width, out.original_height) == (tw, th)
    b64 = base64.standard_b64encode(out.data).decode("ascii")
    fw, fh, _ = measure_base64_image_dimensions(b64)
    assert (fw, fh) == (out.width, out.height)


def test_dimension_error_maps_to_invalid_request_not_incompatible() -> None:
    class FakeApiError(Exception):
        status_code = 400
        body = {"type": "invalid_request_error", "request_id": "req_011Cd4BnV8Y9MpeBmjxZfuAW"}

    exc = FakeApiError(
        "At least one of the image dimensions exceed max allowed size "
        "for many-image requests: 2000 pixels"
    )
    code, details = classify_anthropic_messages_api_error(exc)
    assert code == "PROVIDER_IMAGE_DIMENSION_EXCEEDED"
    assert details.get("request_id") == "req_011Cd4BnV8Y9MpeBmjxZfuAW"
    assert canonical_provider_error_code(code) == PROVIDER_INVALID_REQUEST
    assert provider_error_retryable(code, details_retryable_class=False) is False
    wrapped = LLMProviderError(code=code, message=str(exc), details={**details, "retryable_class": False})
    assert wrapped.canonical_code == PROVIDER_INVALID_REQUEST
    assert "PROVIDER_INCOMPATIBLE_WITH_JOB" not in str(wrapped)


def test_claude_settings_clamps_legacy_2048(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_MULTI_IMAGE_MAX_DIMENSION", raising=False)
    monkeypatch.setenv("ANTHROPIC_VISION_MAX_IMAGE_SIDE", "2048")
    from src.env_settings.grouped_settings import _resolve_claude_multi_image_max_dimension

    assert _resolve_claude_multi_image_max_dimension() == 1800
