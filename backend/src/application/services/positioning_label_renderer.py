"""Shared layout metrics + PositioningLabelRenderer (PNG via Pillow, PDF via ReportLab)."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Literal

import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import mm as rl_mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from src.application.services.positioning_label_presets import (
    PositioningLabelPreset,
    mm_to_px,
)
from src.domain.aisle_location.payload import canonicalize_positioning_payload

LabelFormat = Literal["PDF", "PNG"]


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


class PositioningLabelRenderer:
    """Pure renderer: no auth, no persistence, no HTTP."""

    MARKER_VERSION = 1

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
        return img.resize((marker_px, marker_px), Image.Resampling.NEAREST)

    def _render_png(
        self,
        *,
        qr_text: str,
        display: PositioningLabelDisplayData,
        preset: PositioningLabelPreset,
    ) -> bytes:
        width = mm_to_px(preset.width_mm, preset.dpi)
        height = mm_to_px(preset.height_mm, preset.dpi)
        border = mm_to_px(1.5, preset.dpi)
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [border, border, width - border - 1, height - border - 1],
            outline="black",
            width=max(2, border // 2),
        )
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()
        y = border + mm_to_px(4, preset.dpi)
        x = border + mm_to_px(4, preset.dpi)
        lines = [
            "DINAMIC SYSTEMS",
            "ETIQUETA DE POSICIONAMIENTO",
            "",
            f"Depósito: {display.depot_name}",
            f"Pasillo: {display.aisle_code}",
            f"Posición: {display.position_code}",
        ]
        for line in lines:
            draw.text((x, y), line, fill="black", font=font_lg if line.isupper() else font_sm)
            y += mm_to_px(5.5 if line else 3.0, preset.dpi)

        marker_px = mm_to_px(preset.marker_size_mm, preset.dpi)
        qr_img = self._build_qr_image(qr_text, marker_px)
        qr_x = (width - marker_px) // 2
        qr_y = y + mm_to_px(2, preset.dpi)
        # Keep QR inside bottom margin for footer
        max_qr_y = height - border - mm_to_px(14, preset.dpi) - marker_px
        if qr_y > max_qr_y:
            qr_y = max(border + mm_to_px(30, preset.dpi), max_qr_y)
        img.paste(qr_img, (qr_x, qr_y))

        footer_y = height - border - mm_to_px(10, preset.dpi)
        draw.text(
            (x, footer_y),
            f"ID: {display.public_label_id}",
            fill="black",
            font=font_sm,
        )
        draw.text(
            (x, footer_y + mm_to_px(4, preset.dpi)),
            (
                f"Versión payload={display.payload_version} "
                f"marcador={display.marker_version} plantilla={display.template_version}"
            ),
            fill="black",
            font=font_sm,
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
        # Render QR once via Pillow then embed — shared marker path with PNG.
        marker_px = mm_to_px(preset.marker_size_mm, max(preset.dpi, 200))
        qr_img = self._build_qr_image(qr_text, marker_px)
        qr_buf = io.BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)

        pdf_buf = io.BytesIO()
        page_w = preset.width_mm * rl_mm
        page_h = preset.height_mm * rl_mm
        c = canvas.Canvas(pdf_buf, pagesize=(page_w, page_h))
        margin = 4 * rl_mm
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(1.5)
        c.rect(margin, margin, page_w - 2 * margin, page_h - 2 * margin)

        text_x = margin + 3 * rl_mm
        y = page_h - margin - 8 * rl_mm
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(text_x, y, "DINAMIC SYSTEMS")
        y -= 6 * rl_mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(text_x, y, "ETIQUETA DE POSICIONAMIENTO")
        y -= 8 * rl_mm
        c.setFont("Helvetica", 9)
        for line in (
            f"Depósito: {display.depot_name}",
            f"Pasillo: {display.aisle_code}",
            f"Posición: {display.position_code}",
        ):
            c.drawString(text_x, y, line)
            y -= 5 * rl_mm

        marker_w = preset.marker_size_mm * rl_mm
        qr_x = (page_w - marker_w) / 2
        qr_y = margin + 16 * rl_mm
        c.drawImage(
            ImageReader(qr_buf),
            qr_x,
            qr_y,
            width=marker_w,
            height=marker_w,
            mask="auto",
        )
        c.setFont("Helvetica", 8)
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
