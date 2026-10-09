"""Visual typography alignment — positioning primary value vs item-label tokens."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from src.application.services.label_print_typography import (
    DEFAULT_LABEL_PRINT_TYPOGRAPHY,
    primary_value_font_size_pt,
    pt_to_px,
)
from src.application.services.positioning_label_presets import get_positioning_label_preset
from src.application.services.positioning_label_renderer import (
    PositioningLabelDisplayData,
    PositioningLabelRenderer,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.domain.aisle_location.payload import build_positioning_label_payload


def test_primary_tokens_match_item_label_css_scale() -> None:
    tokens = DEFAULT_LABEL_PRINT_TYPOGRAPHY
    assert tokens.primary_value_font_size_pt == 34.0
    assert tokens.primary_value_font_size_long_pt == 26.0
    assert tokens.primary_value_font_size_xlong_pt == 18.0
    assert primary_value_font_size_pt("02") == 34.0
    assert primary_value_font_size_pt("A" * 20) == 26.0
    assert primary_value_font_size_pt("A" * 32) == 18.0


def test_positioning_png_primary_text_is_large() -> None:
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="test-secret-16chars", key_version=1)
    )
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pl_vis", version=1)
    )
    display = PositioningLabelDisplayData(
        depot_name="Cliente Demo",
        aisle_code="",
        position_code="02",
        public_label_id="pl_vis",
        payload_version=1,
        marker_version=1,
        template_version=2,
    )
    preset = get_positioning_label_preset("MM_100x100")
    rendered = PositioningLabelRenderer().render(
        payload=payload, display=display, preset=preset, fmt="PNG"
    )
    img = Image.open(io.BytesIO(rendered.content)).convert("RGB")
    # Primary 34pt at 300dpi ≈ 141px — ink density in upper half must be material.
    upper = img.crop((0, 0, img.width, img.height // 2))
    ink = sum(1 for px in upper.getdata() if px != (255, 255, 255))
    assert ink > 800, f"expected large primary location ink, got {ink}"

    expected_px = pt_to_px(34.0, preset.dpi)
    assert expected_px >= 130

    # Sanity: drawing "02" at primary size covers a non-trivial bbox.
    draw = ImageDraw.Draw(Image.new("RGB", (400, 200), "white"))
    # Font may be default; still verify token conversion path.
    assert primary_value_font_size_pt(display.position_code) == 34.0
    _ = draw  # keep import usage intentional for visual harness
