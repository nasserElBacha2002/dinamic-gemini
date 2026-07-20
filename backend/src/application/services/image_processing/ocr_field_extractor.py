"""Phase 4 — deterministic OCR field extraction from text blocks / full text.

Does not invent values. Ambiguous equally-plausible candidates are reported, not auto-picked.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

from src.application.ports.internal_label_reader import InternalOcrReadResult, OcrTextBlock

# Label aliases (accent-insensitive matching after normalization).
_CODE_ALIASES = (
    "ean",
    "codigo",
    "cod",
    "cod.",
    "codigo interno",
    "internal code",
    "sku",
)
_ARTICLE_ALIASES = ("articulo", "artículo", "art", "art.", "producto", "product")
_QTY_ALIASES = ("cantidad", "cant", "cant.", "qty", "quantity", "q")
_LOT_ALIASES = ("lote", "lot", "batch")
_EXP_ALIASES = ("vencimiento", "vencimie", "venc", "expiry", "expiration", "caducidad")
_RECEPTION_ALIASES = ("recepcion", "recepción", "reception")
_RESPONSIBLE_ALIASES = ("responsable", "responsible")

_LABEL_VALUE = re.compile(
    r"(?P<label>[A-Za-zÁÉÍÓÚáéíóúÑñ.]+(?:\s+[A-Za-zÁÉÍÓÚáéíóúÑñ.]+)?)\s*[:\-]\s*(?P<value>.+)$",
    re.UNICODE,
)
_EAN_PATTERN = re.compile(r"^\d{8}$|^\d{12,14}$")


class OcrFieldKind(str, Enum):
    INTERNAL_CODE = "internal_code"
    QUANTITY = "quantity"
    EAN = "ean"
    ARTICLE = "article"
    PRODUCT = "product"
    LOT = "lot"
    EXPIRATION = "expiration"
    RECEPTION = "reception"
    RESPONSIBLE = "responsible"


@dataclass(frozen=True)
class OcrFieldCandidate:
    kind: OcrFieldKind
    value: str
    source: str
    associated_text: str
    confidence: float | None
    region: tuple[int, int, int, int] | None
    rule: str


@dataclass
class OcrFieldExtraction:
    internal_code_candidates: list[OcrFieldCandidate] = field(default_factory=list)
    quantity_candidates: list[OcrFieldCandidate] = field(default_factory=list)
    ean_candidates: list[OcrFieldCandidate] = field(default_factory=list)
    article_candidates: list[OcrFieldCandidate] = field(default_factory=list)
    product_candidates: list[OcrFieldCandidate] = field(default_factory=list)
    lot_candidates: list[OcrFieldCandidate] = field(default_factory=list)
    expiration_candidates: list[OcrFieldCandidate] = field(default_factory=list)
    reception_candidates: list[OcrFieldCandidate] = field(default_factory=list)
    responsible_candidates: list[OcrFieldCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _fold(text: str) -> str:
    """Lowercase + strip accents for alias matching."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower().strip()


def _region(block: OcrTextBlock) -> tuple[int, int, int, int] | None:
    if block.left is None or block.top is None or block.width is None or block.height is None:
        return None
    return (int(block.left), int(block.top), int(block.width), int(block.height))


class OcrFieldExtractor:
    """Convert OCR read results into structured field candidates."""

    def extract(self, read: InternalOcrReadResult) -> OcrFieldExtraction:
        out = OcrFieldExtraction()
        lines = self._lines_from_blocks(read.text_blocks)
        if not lines and read.full_text.strip():
            lines = [(ln, None, None) for ln in read.full_text.splitlines() if ln.strip()]

        for text, conf, region in lines:
            self._extract_labeled_line(text, conf, region, out)

        # Spatial: value on the line immediately below a lone label.
        for idx, (text, conf, region) in enumerate(lines):
            folded = _fold(text).rstrip(":")
            if folded in _CODE_ALIASES or folded in _ARTICLE_ALIASES or folded in _QTY_ALIASES:
                if idx + 1 < len(lines):
                    nxt, nconf, nregion = lines[idx + 1]
                    if ":" not in nxt:
                        self._assign_by_label(
                            folded, nxt.strip(), nconf or conf, nregion or region, out, "below_label"
                        )

        if not out.ean_candidates:
            self._scan_bare_eans(lines, out)

        return out

    def _lines_from_blocks(
        self, blocks: tuple[OcrTextBlock, ...]
    ) -> list[tuple[str, float | None, tuple[int, int, int, int] | None]]:
        if not blocks:
            return []
        # Group by (block_num, line_num) when present; else one entry per non-empty block.
        grouped: dict[tuple[int, int], list[OcrTextBlock]] = {}
        singles: list[OcrTextBlock] = []
        for b in blocks:
            text = (b.text or "").strip()
            if not text:
                continue
            if b.block_num is not None and b.line_num is not None:
                grouped.setdefault((int(b.block_num), int(b.line_num)), []).append(b)
            else:
                singles.append(b)

        lines: list[tuple[str, float | None, tuple[int, int, int, int] | None]] = []
        for key in sorted(grouped.keys()):
            parts = sorted(grouped[key], key=lambda x: (x.left or 0))
            text = " ".join((p.text or "").strip() for p in parts if (p.text or "").strip())
            confs = [p.confidence for p in parts if p.confidence is not None]
            conf = sum(confs) / len(confs) if confs else None
            region = _region(parts[0])
            if text:
                for sub in text.splitlines():
                    sub = sub.strip()
                    if sub:
                        lines.append((sub, conf, region))
        for b in singles:
            for sub in (b.text or "").splitlines():
                sub = sub.strip()
                if sub:
                    lines.append((sub, b.confidence, _region(b)))
        return lines

    def _extract_labeled_line(
        self,
        text: str,
        conf: float | None,
        region: tuple[int, int, int, int] | None,
        out: OcrFieldExtraction,
    ) -> None:
        m = _LABEL_VALUE.match(text.strip())
        if not m:
            return
        label = _fold(m.group("label"))
        value = m.group("value").strip()
        self._assign_by_label(label, value, conf, region, out, "labeled_same_line")

    def _assign_by_label(
        self,
        label: str,
        value: str,
        conf: float | None,
        region: tuple[int, int, int, int] | None,
        out: OcrFieldExtraction,
        rule: str,
    ) -> None:
        value = value.strip()
        if not value:
            return
        if label in _QTY_ALIASES:
            out.quantity_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.QUANTITY, value, "label", label, conf, region, rule
                )
            )
            return
        if label == "ean" or label.startswith("ean"):
            out.ean_candidates.append(
                OcrFieldCandidate(OcrFieldKind.EAN, value, "label", label, conf, region, rule)
            )
            out.internal_code_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.INTERNAL_CODE, value, "ean_label", label, conf, region, rule
                )
            )
            return
        if label in _CODE_ALIASES:
            out.internal_code_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.INTERNAL_CODE, value, "label", label, conf, region, rule
                )
            )
            return
        if label in ("articulo", "artículo", "art", "art."):
            out.article_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.ARTICLE, value, "label", label, conf, region, rule
                )
            )
            out.internal_code_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.INTERNAL_CODE, value, "article_label", label, conf, region, rule
                )
            )
            return
        if label in ("producto", "product"):
            out.product_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.PRODUCT, value, "label", label, conf, region, rule
                )
            )
            out.internal_code_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.INTERNAL_CODE, value, "product_label", label, conf, region, rule
                )
            )
            return
        if label in _LOT_ALIASES:
            out.lot_candidates.append(
                OcrFieldCandidate(OcrFieldKind.LOT, value, "label", label, conf, region, rule)
            )
            return
        if label in _EXP_ALIASES:
            out.expiration_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.EXPIRATION, value, "label", label, conf, region, rule
                )
            )
            return
        if label in _RECEPTION_ALIASES:
            out.reception_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.RECEPTION, value, "label", label, conf, region, rule
                )
            )
            return
        if label in _RESPONSIBLE_ALIASES:
            out.responsible_candidates.append(
                OcrFieldCandidate(
                    OcrFieldKind.RESPONSIBLE, value, "label", label, conf, region, rule
                )
            )

    def _scan_bare_eans(
        self,
        lines: list[tuple[str, float | None, tuple[int, int, int, int] | None]],
        out: OcrFieldExtraction,
    ) -> None:
        for text, conf, region in lines:
            for token in re.split(r"\s+", text.strip()):
                if _EAN_PATTERN.fullmatch(token):
                    out.ean_candidates.append(
                        OcrFieldCandidate(
                            OcrFieldKind.EAN, token, "bare_ean", text, conf, region, "bare_ean"
                        )
                    )
                    out.internal_code_candidates.append(
                        OcrFieldCandidate(
                            OcrFieldKind.INTERNAL_CODE,
                            token,
                            "bare_ean",
                            text,
                            conf,
                            region,
                            "bare_ean",
                        )
                    )


__all__ = [
    "OcrFieldCandidate",
    "OcrFieldExtraction",
    "OcrFieldExtractor",
    "OcrFieldKind",
]
