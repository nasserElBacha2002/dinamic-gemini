"""Unit tests for shared multimodal image normalization."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageOps

from src.llm.anthropic_sdk_adapter import (
    _anthropic_build_message_content,
    classify_anthropic_messages_api_error,
)
from src.llm.multimodal_image_normalization import (
    ProviderImageNormalizationError,
    ProviderImagePolicy,
    clear_multimodal_normalize_cache,
    normalize_multimodal_image,
    provider_image_policy_for,
)
from src.llm.types import LLMRequest
from src.pipeline.contracts.analysis_context import AnalysisContext, VisualReferenceContext
from src.pipeline.services.analysis_visual_reference_prep import prepare_visual_reference_inputs


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_multimodal_normalize_cache()
    yield
    clear_multimodal_normalize_cache()


def _jpeg_bytes(w: int, h: int, *, color: tuple[int, int, int] = (40, 80, 120)) -> bytes:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _policy(max_dimension: int = 1800, jpeg_quality: int = 88) -> ProviderImagePolicy:
    return provider_image_policy_for("claude", max_dimension=max_dimension, jpeg_quality=jpeg_quality)


def test_no_resize_when_under_limit() -> None:
    raw = _jpeg_bytes(1280, 720)
    out = normalize_multimodal_image(
        raw, source_id="IMG_001", role="primary_evidence", policy=_policy()
    )
    assert out.was_resized is False
    assert out.width == 1280
    assert out.height == 720


def test_horizontal_large_resizes_to_1800() -> None:
    raw = _jpeg_bytes(4000, 3000)
    out = normalize_multimodal_image(
        raw, source_id="REF_001", role="visual_reference", policy=_policy()
    )
    assert out.was_resized is True
    assert out.width == 1800
    assert out.height == 1350
    assert max(out.width, out.height) <= 1800


def test_vertical_large_resizes_to_1800() -> None:
    raw = _jpeg_bytes(1200, 3000)
    out = normalize_multimodal_image(
        raw, source_id="REF_002", role="visual_reference", policy=_policy()
    )
    assert out.was_resized is True
    assert out.width == 720
    assert out.height == 1800


def test_exact_limit_no_resize() -> None:
    raw = _jpeg_bytes(1800, 1000)
    out = normalize_multimodal_image(
        raw, source_id="x", role="primary_evidence", policy=_policy()
    )
    assert out.was_resized is False
    assert out.width == 1800
    assert out.height == 1000


def test_png_alpha_composites_on_white() -> None:
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out = normalize_multimodal_image(
        buf.getvalue(), source_id="a", role="primary_evidence", policy=_policy()
    )
    decoded = Image.open(io.BytesIO(out.data)).convert("RGB")
    # Transparent → white background, not black.
    assert decoded.getpixel((50, 50)) == (255, 255, 255)


def test_cmyk_converts_to_rgb_jpeg() -> None:
    img = Image.new("CMYK", (64, 64), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    out = normalize_multimodal_image(
        buf.getvalue(), source_id="c", role="primary_evidence", policy=_policy()
    )
    assert out.mime_type == "image/jpeg"
    Image.open(io.BytesIO(out.data)).convert("RGB")


def test_exif_transpose_before_measure(tmp_path: Path) -> None:
    # Orientation 6: stored as landscape but displayed as portrait after transpose.
    img = Image.new("RGB", (200, 100), (10, 20, 30))
    # Attach EXIF orientation via piexif if available; else simulate with ImageOps.
    # Without piexif, build an image that ImageOps.exif_transpose leaves as-is and
    # separately assert transpose-aware helper path via a transposed save.
    exif = img.getexif()
    exif[274] = 6  # Orientation tag
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, exif=exif)
    raw = buf.getvalue()
    # After EXIF orientation=6, displayed size should swap.
    with Image.open(io.BytesIO(raw)) as opened:
        transposed = ImageOps.exif_transpose(opened)
        assert transposed is not None
        tw, th = transposed.size
    out = normalize_multimodal_image(
        raw, source_id="e", role="primary_evidence", policy=_policy(max_dimension=1800)
    )
    assert (out.original_width, out.original_height) == (tw, th)


def test_corrupt_bytes_raise_specific_error() -> None:
    with pytest.raises(ProviderImageNormalizationError) as ei:
        normalize_multimodal_image(
            b"not-an-image",
            source_id="bad",
            role="visual_reference",
            policy=_policy(),
        )
    assert ei.value.code == "PROVIDER_IMAGE_NORMALIZATION_FAILED"


def test_prepare_references_load_originals_keep_ids_order(tmp_path: Path) -> None:
    p1 = tmp_path / "ref1.jpg"
    p2 = tmp_path / "ref2.jpg"
    Image.new("RGB", (4032, 3024), (1, 2, 3)).save(p1, format="JPEG")
    Image.new("RGB", (1200, 2500), (4, 5, 6)).save(p2, format="JPEG")
    ctx = AnalysisContext(
        primary_evidence=[],
        instructions=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="REF_001",
                source_path=str(p1),
                resolved_path=str(p1),
                mime_type="image/jpeg",
            ),
            VisualReferenceContext(
                reference_id="REF_002",
                source_path=str(p2),
                resolved_path=str(p2),
                mime_type="image/jpeg",
            ),
        ],
    )
    policy = _policy(1800)
    loaded, attachments, ids = prepare_visual_reference_inputs(
        ctx, job_id="job-1", image_policy=policy
    )
    assert ids == ["REF_001", "REF_002"]
    assert [a["reference_id"] for a in attachments] == ["REF_001", "REF_002"]
    assert all(a["role"] == "visual_reference" for a in attachments)
    assert len(loaded) == 2
    # Prep no longer resizes — adapter/final gate owns provider policy.
    assert loaded[0].size == (4032, 3024)
    assert loaded[1].size == (1200, 2500)


def test_prepare_corrupt_reference_skipped_with_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not-jpeg")
    good = tmp_path / "good.jpg"
    Image.new("RGB", (640, 480), (1, 1, 1)).save(good, format="JPEG")
    # load_pil_from_path uses cv2.imread which returns None for corrupt → skip before normalize.
    # Also cover normalize failure: valid path that open fails after mock is harder; use missing+good.
    ctx = AnalysisContext(
        primary_evidence=[],
        instructions=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="REF_BAD",
                source_path=str(bad),
                resolved_path=str(bad),
                mime_type="image/jpeg",
            ),
            VisualReferenceContext(
                reference_id="REF_OK",
                source_path=str(good),
                resolved_path=str(good),
                mime_type="image/jpeg",
            ),
        ],
    )
    loaded, attachments, ids = prepare_visual_reference_inputs(
        ctx, job_id="job-1", image_policy=_policy()
    )
    assert ids == ["REF_OK"]
    assert len(loaded) == 1
    assert attachments[0]["resolved"] is False
    assert attachments[1]["resolved"] is True


def test_claude_classifier_maps_dimension_exceeded() -> None:
    class FakeApiError(Exception):
        status_code = 400
        body = {"type": "invalid_request_error", "request_id": "req_abc"}

    exc = FakeApiError(
        "At least one of the image dimensions exceed max allowed size for many-image requests: 2000 pixels"
    )
    code, details = classify_anthropic_messages_api_error(exc)
    assert code == "PROVIDER_IMAGE_DIMENSION_EXCEEDED"
    assert details.get("request_id") == "req_abc"
    assert details.get("provider") == "claude"


def test_claude_request_20_primary_plus_2_large_refs_all_within_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: 20×1280 primaries + 2 oversized refs → all final ≤ 1800, 22 images."""
    settings = SimpleNamespace(
        anthropic_image_jpeg_quality=88,
    )
    primaries = [np.zeros((720, 1280, 3), dtype=np.uint8) for _ in range(20)]
    # Pass original oversized refs; adapter + final gate must normalize once.
    refs = [
        Image.new("RGB", (4032, 3024), (10, 20, 30)),
        Image.new("RGB", (1200, 2500), (40, 50, 60)),
    ]

    request = LLMRequest(
        job_id="job-reg",
        frames=[],
        frame_refs=[f"IMG_{i:03d}" for i in range(1, 21)],
        prompt="analyze",
        schema_version="v2.1",
        frames_nd=primaries,
        context_images=refs,
        metadata={"reference_image_ids": ["REF_001", "REF_002"]},
    )
    # Avoid serialized path
    monkeypatch.setattr(
        "src.llm.anthropic_sdk_adapter.resolve_serialized_payload_for_adapter",
        lambda *a, **k: None,
    )
    content = _anthropic_build_message_content(
        request, settings, primaries, 1800, effective_model="claude-test"
    )
    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == 22
    for block in image_blocks:
        raw_b64 = block["source"]["data"]
        import base64

        raw = base64.standard_b64decode(raw_b64)
        with Image.open(io.BytesIO(raw)) as im:
            assert max(im.size) <= 1800
        assert block["source"]["media_type"] == "image/jpeg"


def test_gemini_policy_compatible_normalize_keeps_ids() -> None:
    policy = provider_image_policy_for("gemini", max_dimension=1280, jpeg_quality=85)
    raw = _jpeg_bytes(2000, 1500)
    out = normalize_multimodal_image(
        raw, source_id="REF_G", role="visual_reference", policy=policy
    )
    assert out.source_id == "REF_G"
    assert out.role == "visual_reference"
    assert max(out.width, out.height) <= 1280
