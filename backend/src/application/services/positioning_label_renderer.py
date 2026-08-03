"""Shared layout metrics + PositioningLabelRenderer (PNG via Pillow, PDF via ReportLab).

Primary location code uses the same typographic scale as item-label Código/Cantidad
(see ``label_print_typography.DEFAULT_LABEL_PRINT_TYPOGRAPHY``).
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import mm as rl_mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from src.application.services.label_print_typography import (
    DEFAULT_LABEL_PRINT_TYPOGRAPHY,
    LabelPrintTypographyTokens,
    primary_value_font_size_pt,
    pt_to_px,
)
from src.application.services.positioning_label_presets import (
    PositioningLabelPreset,
    mm_to_px,
)
from src.domain.aisle_location.payload import canonicalize_positioning_payload

LabelFormat = Literal["PDF", "PNG"]
PillowFont = ImageFont.ImageFont | ImageFont.FreeTypeFont

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


@dataclass(frozen=True)
class PositioningLabelDisplayData:
    depot_name: str
    aisle_code: str
    position_code: str
    public_label_id: str
    payload_version: int
    marker_version: int
    template_version: int


@dataclass(frozen=True)
class RenderedPositioningLabel:
    content: bytes
    content_type: str
    artifact_hash: str
    format: LabelFormat
    preset: str
    template_version: int
    marker_version: int


def _load_font(size_px: int, *, bold: bool = True) -> PillowFont:
    for path in _FONT_CANDIDATES:
        if not Path(path).is_file():
            continue
        try:
            return ImageFont.truetype(path, size_px)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_primary_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    max_width: int,
    dpi: int,
    tokens: LabelPrintTypographyTokens,
) -> PillowFont:
    size_pt = primary_value_font_size_pt(text, tokens)
    min_pt = tokens.primary_value_min_font_size_pt
    while size_pt >= min_pt:
        font = _load_font(pt_to_px(size_pt, dpi), bold=True)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            return font
        size_pt -= 2.0
    return _load_font(pt_to_px(min_pt, dpi), bold=True)


def _wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: PillowFont, max_width: int
) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines[:2]


class PositioningLabelRenderer:
    """Pure renderer: no auth, no persistence, no HTTP."""

    MARKER_VERSION = 1

    def __init__(self, typography: LabelPrintTypographyTokens | None = None) -> None:
        self._typo = typography or DEFAULT_LABEL_PRINT_TYPOGRAPHY

    def render(
        self,
        *,
        payload: dict,
        display: PositioningLabelDisplayData,
        preset: PositioningLabelPreset,
        fmt: LabelFormat,
    ) -> RenderedPositioningLabel:
        qr_text = canonicalize_positioning_payload(payload)
        if fmt == "PNG":
            content = self._render_png(qr_text=qr_text, display=display, preset=preset)
            content_type = "image/png"
        elif fmt == "PDF":
            content = self._render_pdf(qr_text=qr_text, display=display, preset=preset)
            content_type = "application/pdf"
        else:
            raise ValueError(f"Unsupported format: {fmt}")
        digest = hashlib.sha256(content).hexdigest()
        return RenderedPositioningLabel(
            content=content,
            content_type=content_type,
            artifact_hash=digest,
            format=fmt,
            preset=preset.code,
            template_version=int(preset.template_version),
            marker_version=int(display.marker_version or self.MARKER_VERSION),
        )

    def _build_qr_image(self, qr_text: str, marker_px: int) -> Image.Image:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        return cast(
            Image.Image,
            img.resize((marker_px, marker_px), Image.Resampling.NEAREST),
        )

    def _render_png(
        self,
        *,
        qr_text: str,
        display: PositioningLabelDisplayData,
        preset: PositioningLabelPreset,
    ) -> bytes:
        tokens = self._typo
        width = mm_to_px(preset.width_mm, preset.dpi)
        height = mm_to_px(preset.height_mm, preset.dpi)
        margin = mm_to_px(tokens.print_margin_mm, preset.dpi)
        gap = mm_to_px(tokens.content_gap_mm, preset.dpi)
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [margin // 2, margin // 2, width - margin // 2 - 1, height - margin // 2 - 1],
            outline="black",
            width=max(2, margin // 8),
        )

        font_brand = _load_font(pt_to_px(tokens.brand_font_size_pt, preset.dpi), bold=True)
        font_title = _load_font(pt_to_px(tokens.title_font_size_pt, preset.dpi), bold=True)
        font_secondary = _load_font(pt_to_px(tokens.secondary_text_font_size_pt, preset.dpi), bold=False)
        font_footer = _load_font(pt_to_px(tokens.footer_font_size_pt, preset.dpi), bold=False)

        x = margin
        y = margin
        draw.text((x, y), "DINAMIC SYSTEMS", fill="black", font=font_brand)
        y += pt_to_px(tokens.brand_font_size_pt, preset.dpi) + gap // 2
        draw.text((x, y), "ETIQUETA DE POSICIONAMIENTO", fill="black", font=font_title)
        y += pt_to_px(tokens.title_font_size_pt, preset.dpi) + gap

        if (display.depot_name or "").strip():
            draw.text(
                (x, y),
                f"Cliente: {display.depot_name.strip()}",
                fill="black",
                font=font_secondary,
            )
            y += pt_to_px(tokens.secondary_text_font_size_pt, preset.dpi) + gap // 2

        position = (display.position_code or "").strip() or "—"
        caption_font = _load_font(pt_to_px(tokens.primary_label_font_size_pt, preset.dpi), bold=True)
        draw.text((x, y), "UBICACIÓN", fill="black", font=caption_font)
        y += pt_to_px(tokens.primary_label_font_size_pt, preset.dpi) + gap // 2

        text_max_width = width - 2 * margin
        primary_font = _fit_primary_font(
            draw, position, max_width=text_max_width, dpi=preset.dpi, tokens=tokens
        )
        for line in _wrap_text(draw, position, primary_font, text_max_width):
            draw.text((x, y), line, fill="black", font=primary_font)
            bbox = cast(
                tuple[int, int, int, int],
                draw.textbbox((0, 0), line, font=primary_font),
            )
            y += (bbox[3] - bbox[1]) + gap // 3

        footer_block = mm_to_px(12, preset.dpi)
        marker_px = mm_to_px(preset.marker_size_mm, preset.dpi)
        # Prefer leaving room for large primary text; shrink QR only if needed.
        available_for_qr = height - y - footer_block - margin - gap
        if available_for_qr < marker_px:
            marker_px = max(mm_to_px(28, preset.dpi), available_for_qr)
        qr_img = self._build_qr_image(qr_text, marker_px)
        qr_x = (width - marker_px) // 2
        qr_y = y + gap
        max_qr_y = height - margin - footer_block - marker_px
        if qr_y > max_qr_y:
            qr_y = max(y, max_qr_y)
        img.paste(qr_img, (qr_x, qr_y))

        footer_y = height - margin - footer_block + mm_to_px(2, preset.dpi)
        draw.text((x, footer_y), f"ID: {display.public_label_id}", fill="black", font=font_footer)
        draw.text(
            (x, footer_y + mm_to_px(4, preset.dpi)),
            (
                f"Versión payload={display.payload_version} "
                f"marcador={display.marker_version} plantilla={display.template_version}"
            ),
            fill="black",
            font=font_footer,
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def _render_pdf(
        self,
        *,
        qr_text: str,
        display: PositioningLabelDisplayData,
        preset: PositioningLabelPreset,
    ) -> bytes:
        tokens = self._typo
        marker_px = mm_to_px(preset.marker_size_mm, max(preset.dpi, 200))
        qr_img = self._build_qr_image(qr_text, marker_px)
        qr_buf = io.BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)

        pdf_buf = io.BytesIO()
        page_w = preset.width_mm * rl_mm
        page_h = preset.height_mm * rl_mm
        c = canvas.Canvas(pdf_buf, pagesize=(page_w, page_h))
        margin = tokens.print_margin_mm * rl_mm
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(1.5)
        c.rect(margin / 2, margin / 2, page_w - margin, page_h - margin)

        text_x = margin
        y = page_h - margin - tokens.brand_font_size_pt * 0.35 * rl_mm
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", tokens.brand_font_size_pt)
        c.drawString(text_x, y, "DINAMIC SYSTEMS")
        y -= (tokens.title_font_size_pt + 2) * 0.5 * rl_mm
        c.setFont("Helvetica-Bold", tokens.title_font_size_pt)
        c.drawString(text_x, y, "ETIQUETA DE POSICIONAMIENTO")
        y -= tokens.content_gap_mm * rl_mm

        if (display.depot_name or "").strip():
            c.setFont("Helvetica", tokens.secondary_text_font_size_pt)
            c.drawString(text_x, y, f"Cliente: {display.depot_name.strip()}")
            y -= (tokens.secondary_text_font_size_pt + 2) * 0.45 * rl_mm

        c.setFont("Helvetica-Bold", tokens.primary_label_font_size_pt)
        c.drawString(text_x, y, "UBICACIÓN")
        y -= (tokens.primary_label_font_size_pt + 4) * 0.45 * rl_mm

        position = (display.position_code or "").strip() or "—"
        primary_pt = primary_value_font_size_pt(position, tokens)
        max_text_w = page_w - 2 * margin
        while primary_pt >= tokens.primary_value_min_font_size_pt:
            c.setFont("Helvetica-Bold", primary_pt)
            if c.stringWidth(position, "Helvetica-Bold", primary_pt) <= max_text_w:
                break
            primary_pt -= 2.0
        c.setFont("Helvetica-Bold", primary_pt)
        # Up to two lines for long names
        words = position.split()
        lines: list[str] = []
        if not words:
            lines = [position]
        else:
            cur = words[0]
            for w in words[1:]:
                trial = f"{cur} {w}"
                if c.stringWidth(trial, "Helvetica-Bold", primary_pt) <= max_text_w:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
        for line in lines[:2]:
            c.drawString(text_x, y, line)
            y -= primary_pt * 0.45 * rl_mm

        marker_w = preset.marker_size_mm * rl_mm
        footer_h = 14 * rl_mm
        qr_y = margin + footer_h
        # If primary text consumed space, keep QR above footer without overlapping text.
        max_qr_top = y - tokens.content_gap_mm * rl_mm
        if qr_y + marker_w > max_qr_top and max_qr_top - margin > 28 * rl_mm:
            marker_w = max(28 * rl_mm, max_qr_top - margin - tokens.content_gap_mm * rl_mm)
            qr_y = margin + footer_h
        qr_x = (page_w - marker_w) / 2
        c.drawImage(
            ImageReader(qr_buf),
            qr_x,
            qr_y,
            width=marker_w,
            height=marker_w,
            mask="auto",
            preserveAspectRatio=True,
        )
        c.setFont("Helvetica", tokens.footer_font_size_pt)
        c.drawString(text_x, margin + 8 * rl_mm, f"ID: {display.public_label_id}")
        c.drawString(
            text_x,
            margin + 4 * rl_mm,
            (
                f"Versión payload={display.payload_version} "
                f"marcador={display.marker_version} plantilla={display.template_version}"
            ),
        )
        c.showPage()
        c.save()
        return pdf_buf.getvalue()
