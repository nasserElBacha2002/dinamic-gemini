"""Shared layout metrics + PositioningLabelRenderer (PNG via Pillow, PDF via ReportLab).

Primary location code uses the same typographic scale as item-label Código/Cantidad
(see ``label_print_typography.DEFAULT_LABEL_PRINT_TYPOGRAPHY``).

Hierarchy labels (pallet/side/level/marker) use a compact field layout so QR stays
scannable on MM_100x100 without overlapping footer text.
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
from src.domain.client_position_label.hierarchy import (
    PositionHierarchy,
    PositionSide,
    localize_side_es,
)

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

# Minimum QR edge for warehouse scan reliability on 100×100mm labels.
_MIN_QR_MM = 32.0
_FOOTER_MM = 10.0


@dataclass(frozen=True)
class PositioningLabelDisplayData:
    depot_name: str
    aisle_code: str
    position_code: str
    public_label_id: str
    payload_version: int
    marker_version: int
    template_version: int
    pallet: str | None = None
    side: str | None = None
    level: int | None = None
    marker_index: int | None = None
    marker_total: int | None = None

    @property
    def has_hierarchy(self) -> bool:
        return (
            bool((self.pallet or "").strip())
            and bool((self.side or "").strip())
            and self.level is not None
            and self.marker_index is not None
            and self.marker_total is not None
        )


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


def _hierarchy_rows(display: PositioningLabelDisplayData) -> tuple[tuple[str, str], ...] | None:
    try:
        hierarchy = PositionHierarchy(
            pallet=str(display.pallet),
            side=PositionSide(str(display.side).strip().upper()),
            level=int(display.level),  # type: ignore[arg-type]
            marker_index=int(display.marker_index),  # type: ignore[arg-type]
            marker_total=int(display.marker_total),  # type: ignore[arg-type]
        )
        side_es = localize_side_es(hierarchy.side)
        return (
            ("ID ETIQUETA", display.public_label_id),
            ("PALLET", hierarchy.pallet),
            ("LADO", side_es),
            ("NIVEL", str(hierarchy.level)),
            ("MARBETE", hierarchy.formatted_marker_pair()),
        )
    except (TypeError, ValueError):
        return None


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
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(qr_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        return cast(
            Image.Image,
            img.resize((marker_px, marker_px), Image.Resampling.NEAREST),
        )

    def _reserved_qr_px(self, *, preset: PositioningLabelPreset, content_top_y: int) -> tuple[int, int]:
        """Return (qr_edge_px, qr_top_y) with QR above footer, never overlapping fields."""
        margin = mm_to_px(self._typo.print_margin_mm, preset.dpi)
        gap = mm_to_px(self._typo.content_gap_mm, preset.dpi)
        footer = mm_to_px(_FOOTER_MM, preset.dpi)
        height = mm_to_px(preset.height_mm, preset.dpi)
        max_qr = mm_to_px(preset.marker_size_mm, preset.dpi)
        min_qr = mm_to_px(_MIN_QR_MM, preset.dpi)
        available = height - content_top_y - footer - margin - gap
        qr_px = min(max_qr, max(min_qr, available))
        if available < min_qr:
            # Still reserve min QR; fields must fit above this line.
            qr_px = min_qr
        qr_y = height - margin - footer - qr_px
        return qr_px, qr_y

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
        font_field_label = _load_font(pt_to_px(9.0, preset.dpi), bold=True)
        font_field_value = _load_font(pt_to_px(16.0, preset.dpi), bold=True)
        font_marbete = _load_font(pt_to_px(22.0, preset.dpi), bold=True)

        # Reserve QR + footer first so hierarchy text cannot push QR off-canvas.
        # Estimate content start after header; QR reservation uses mid-band heuristic.
        header_estimate = (
            margin
            + pt_to_px(tokens.brand_font_size_pt, preset.dpi)
            + pt_to_px(tokens.title_font_size_pt, preset.dpi)
            + pt_to_px(tokens.secondary_text_font_size_pt, preset.dpi)
            + 3 * gap
        )
        qr_px, qr_y = self._reserved_qr_px(preset=preset, content_top_y=header_estimate)
        content_bottom = qr_y - gap

        x = margin
        y = margin
        draw.text((x, y), "DINAMIC SYSTEMS", fill="black", font=font_brand)
        y += pt_to_px(tokens.brand_font_size_pt, preset.dpi) + gap // 2
        draw.text((x, y), "ETIQUETA DE POSICIONAMIENTO", fill="black", font=font_title)
        y += pt_to_px(tokens.title_font_size_pt, preset.dpi) + gap // 2

        if (display.depot_name or "").strip():
            draw.text(
                (x, y),
                f"Cliente: {display.depot_name.strip()}",
                fill="black",
                font=font_secondary,
            )
            y += pt_to_px(tokens.secondary_text_font_size_pt, preset.dpi) + gap // 2

        text_max_width = width - 2 * margin
        hierarchy_rows = _hierarchy_rows(display) if display.has_hierarchy else None

        if hierarchy_rows:
            for caption, value in hierarchy_rows:
                if y >= content_bottom - mm_to_px(6, preset.dpi):
                    break
                value_font = font_marbete if caption == "MARBETE" else font_field_value
                if caption == "ID ETIQUETA":
                    value_font = _load_font(pt_to_px(11.0, preset.dpi), bold=True)
                draw.text((x, y), caption, fill="black", font=font_field_label)
                y += pt_to_px(9.0, preset.dpi) + gap // 5
                for line in _wrap_text(draw, value, value_font, text_max_width):
                    if y >= content_bottom:
                        break
                    draw.text((x, y), line, fill="black", font=value_font)
                    bbox = cast(
                        tuple[int, int, int, int],
                        draw.textbbox((0, 0), line, font=value_font),
                    )
                    y += (bbox[3] - bbox[1]) + gap // 6
                y += gap // 4
        else:
            caption_font = _load_font(pt_to_px(tokens.primary_label_font_size_pt, preset.dpi), bold=True)
            position = (display.position_code or "").strip() or "—"
            draw.text((x, y), "UBICACIÓN", fill="black", font=caption_font)
            y += pt_to_px(tokens.primary_label_font_size_pt, preset.dpi) + gap // 2
            primary_font = _fit_primary_font(
                draw, position, max_width=text_max_width, dpi=preset.dpi, tokens=tokens
            )
            for line in _wrap_text(draw, position, primary_font, text_max_width):
                if y >= content_bottom:
                    break
                draw.text((x, y), line, fill="black", font=primary_font)
                bbox = cast(
                    tuple[int, int, int, int],
                    draw.textbbox((0, 0), line, font=primary_font),
                )
                y += (bbox[3] - bbox[1]) + gap // 3

        # Always paint QR in the reserved band (may shrink slightly if header grew).
        if y + gap > qr_y:
            qr_px, qr_y = self._reserved_qr_px(preset=preset, content_top_y=y)
            # If still tight, shrink QR toward min but keep it on-canvas.
            footer = mm_to_px(_FOOTER_MM, preset.dpi)
            max_edge = height - y - footer - margin - gap
            if max_edge > 0:
                qr_px = max(mm_to_px(_MIN_QR_MM, preset.dpi) // 2, min(qr_px, max_edge))
                qr_y = height - margin - footer - qr_px

        qr_img = self._build_qr_image(qr_text, qr_px)
        qr_x = (width - qr_px) // 2
        img.paste(qr_img, (qr_x, max(margin, qr_y)))

        footer_y = height - margin - mm_to_px(_FOOTER_MM, preset.dpi) + mm_to_px(1.5, preset.dpi)
        # Footer only when hierarchy already showed ID ETIQUETA — keep meta short.
        if not hierarchy_rows:
            draw.text((x, footer_y), f"ID: {display.public_label_id}", fill="black", font=font_footer)
            footer_y += mm_to_px(3.5, preset.dpi)
        draw.text(
            (x, footer_y),
            (
                f"v{display.payload_version} "
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
        page_w = preset.width_mm * rl_mm
        page_h = preset.height_mm * rl_mm
        margin = tokens.print_margin_mm * rl_mm
        gap = tokens.content_gap_mm * rl_mm
        footer_h = _FOOTER_MM * rl_mm
        min_qr = _MIN_QR_MM * rl_mm
        max_qr = preset.marker_size_mm * rl_mm

        # Reserve QR from bottom.
        qr_size = min(max_qr, max(min_qr, page_h * 0.38))
        qr_y = margin + footer_h
        content_bottom_y = qr_y + qr_size + gap

        marker_px = mm_to_px(qr_size / rl_mm, max(preset.dpi, 200))
        qr_img = self._build_qr_image(qr_text, marker_px)
        qr_buf = io.BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)

        pdf_buf = io.BytesIO()
        c = canvas.Canvas(pdf_buf, pagesize=(page_w, page_h))
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
        y -= gap * 0.7

        if (display.depot_name or "").strip():
            c.setFont("Helvetica", tokens.secondary_text_font_size_pt)
            c.drawString(text_x, y, f"Cliente: {display.depot_name.strip()}")
            y -= (tokens.secondary_text_font_size_pt + 2) * 0.45 * rl_mm

        hierarchy_rows = _hierarchy_rows(display) if display.has_hierarchy else None
        max_text_w = page_w - 2 * margin
        if hierarchy_rows:
            for caption, value in hierarchy_rows:
                if y < content_bottom_y + 4 * rl_mm:
                    break
                c.setFont("Helvetica-Bold", 8)
                c.drawString(text_x, y, caption)
                y -= 9 * 0.45 * rl_mm
                value_pt = 18.0 if caption == "MARBETE" else (10.0 if caption == "ID ETIQUETA" else 14.0)
                c.setFont("Helvetica-Bold", value_pt)
                # Single line truncate if needed
                shown = value
                while (
                    c.stringWidth(shown, "Helvetica-Bold", value_pt) > max_text_w
                    and len(shown) > 4
                ):
                    shown = shown[:-1]
                if shown != value:
                    shown = shown[:-1] + "…"
                c.drawString(text_x, y, shown)
                y -= value_pt * 0.5 * rl_mm
        else:
            c.setFont("Helvetica-Bold", tokens.primary_label_font_size_pt)
            c.drawString(text_x, y, "UBICACIÓN")
            y -= (tokens.primary_label_font_size_pt + 4) * 0.45 * rl_mm
            position = (display.position_code or "").strip() or "—"
            primary_pt = primary_value_font_size_pt(position, tokens)
            while primary_pt >= tokens.primary_value_min_font_size_pt:
                c.setFont("Helvetica-Bold", primary_pt)
                if c.stringWidth(position, "Helvetica-Bold", primary_pt) <= max_text_w:
                    break
                primary_pt -= 2.0
            c.setFont("Helvetica-Bold", primary_pt)
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
                if y < content_bottom_y + 4 * rl_mm:
                    break
                c.drawString(text_x, y, line)
                y -= primary_pt * 0.45 * rl_mm

        qr_x = (page_w - qr_size) / 2
        c.drawImage(
            ImageReader(qr_buf),
            qr_x,
            qr_y,
            width=qr_size,
            height=qr_size,
            mask="auto",
            preserveAspectRatio=True,
        )
        c.setFont("Helvetica", tokens.footer_font_size_pt)
        if not hierarchy_rows:
            c.drawString(text_x, margin + 6 * rl_mm, f"ID: {display.public_label_id}")
        c.drawString(
            text_x,
            margin + 3 * rl_mm,
            (
                f"v{display.payload_version} "
                f"marcador={display.marker_version} plantilla={display.template_version}"
            ),
        )
        c.showPage()
        c.save()
        return pdf_buf.getvalue()
