"""Shared print typography tokens — item labels (CSS) and positioning labels (PNG/PDF).

Item label CSS source of truth (frontend labelPrint.css):
  -- primary value (Código / Cantidad): 34pt, weight 900
  -- primary caption: 14pt, weight 800
  -- long / xlong adaptive: 26pt / 18pt
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LabelPrintTypographyTokens:
    """Point sizes aligned with warehouse item-label primary values."""

    primary_value_font_size_pt: float = 34.0
    primary_value_font_size_long_pt: float = 26.0
    primary_value_font_size_xlong_pt: float = 18.0
    primary_value_min_font_size_pt: float = 14.0
    primary_label_font_size_pt: float = 14.0
    secondary_text_font_size_pt: float = 9.0
    brand_font_size_pt: float = 11.0
    title_font_size_pt: float = 10.0
    footer_font_size_pt: float = 8.0
    primary_value_long_min_chars: int = 20
    primary_value_xlong_min_chars: int = 32
    print_margin_mm: float = 4.0
    content_gap_mm: float = 3.0
    qr_quiet_zone_mm: float = 4.0


DEFAULT_LABEL_PRINT_TYPOGRAPHY = LabelPrintTypographyTokens()


def primary_value_font_size_pt(text: str, tokens: LabelPrintTypographyTokens | None = None) -> float:
    """Adaptive primary size matching frontend getLabelCodeMainValueClassName."""
    t = tokens or DEFAULT_LABEL_PRINT_TYPOGRAPHY
    length = len((text or "").strip())
    if length >= t.primary_value_xlong_min_chars:
        return t.primary_value_font_size_xlong_pt
    if length >= t.primary_value_long_min_chars:
        return t.primary_value_font_size_long_pt
    return t.primary_value_font_size_pt


def pt_to_px(pt: float, dpi: int) -> int:
    return max(1, int(round(float(pt) * float(dpi) / 72.0)))
