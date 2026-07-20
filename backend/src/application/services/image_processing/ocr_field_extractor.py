"""Phase 4 — deterministic OCR field extraction from text blocks / full text.

Does not invent values. Ambiguous equally-plausible candidates are reported, not auto-picked.
Produces candidates + evidence; does not decide final ImageResultStatus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.application.ports.internal_label_reader import InternalOcrReadResult, OcrTextBlock
from src.application.services.image_processing.ocr_anchor_matcher import (
    AnchorMatchMode,
    OcrAnchorMatcher,
)
from src.application.services.image_processing.ocr_numeric_candidate_generator import (
    OcrNumericCandidateGenerator,
    mask_value,
)
from src.application.services.image_processing.ocr_spatial_relation_evaluator import (
    BoundingBox,
    OcrSpatialRelationEvaluator,
)
from src.application.services.image_processing.ocr_token_normalizer import (
    NormalizedOcrToken,
    OcrTokenNormalizer,
    fold_ocr_text,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    UnanchoredCodeCandidatePolicy,
    default_extraction_configuration,
)

# Default aliases when no profile is provided (accent-insensitive after fold).
_CODE_ALIASES = (
    "ean",
    "codigo",
    "cod",
    "cod.",
    "codigo interno",
    "cod. interno",
    "internal code",
    "sku",
)
_ARTICLE_ALIASES = ("articulo", "artículo", "art", "art.", "producto", "product")
_QTY_ALIASES = (
    "cantidad",
    "cant",
    "cant.",
    "cant. total",
    "cant total",
    "qty",
    "quantity",
    "q",
    "unidades",
)
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
    extraction_method: str = "LABELED_EXACT"
    anchor_text: str | None = None
    anchor_bbox: tuple[int, int, int, int] | None = None
    spatial_relation: str | None = None
    normalized_distance: float | None = None
    neighbor_text: str | None = None
    line_num: int | None = None
    block_num: int | None = None


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
    stats: dict[str, Any] = field(default_factory=dict)
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)
    matched_anchors: list[dict[str, Any]] = field(default_factory=list)


def _fold(text: str) -> str:
    return fold_ocr_text(text)


def _region(block: OcrTextBlock) -> tuple[int, int, int, int] | None:
    if block.left is None or block.top is None or block.width is None or block.height is None:
        return None
    return (int(block.left), int(block.top), int(block.width), int(block.height))


def _horizontal_overlap(
    a: tuple[int, int, int, int] | None, b: tuple[int, int, int, int] | None
) -> bool:
    if a is None or b is None:
        return True
    a_left, _, a_width, _ = a
    b_left, _, b_width, _ = b
    a_right = a_left + a_width
    b_right = b_left + b_width
    overlap = min(a_right, b_right) - max(a_left, b_left)
    if overlap > 0:
        return True
    gap = -overlap
    return gap <= (a_width / 2)


def _to_bbox(region: tuple[int, int, int, int] | None) -> BoundingBox | None:
    if region is None:
        return None
    return BoundingBox(left=region[0], top=region[1], width=region[2], height=region[3])


class OcrFieldExtractor:
    """Convert OCR read results into structured field candidates."""

    def __init__(
        self,
        *,
        configuration: ExtractionProfileConfiguration | None = None,
        token_normalizer: OcrTokenNormalizer | None = None,
        anchor_matcher: OcrAnchorMatcher | None = None,
        numeric_generator: OcrNumericCandidateGenerator | None = None,
        spatial_evaluator: OcrSpatialRelationEvaluator | None = None,
    ) -> None:
        self._configuration = configuration
        self._normalizer = token_normalizer or OcrTokenNormalizer()
        self._anchor_matcher = anchor_matcher or OcrAnchorMatcher(mode=AnchorMatchMode.FUZZY)
        self._numeric_generator = numeric_generator or OcrNumericCandidateGenerator()
        self._spatial = spatial_evaluator or OcrSpatialRelationEvaluator()

    def extract(
        self,
        read: InternalOcrReadResult,
        *,
        configuration: ExtractionProfileConfiguration | None = None,
    ) -> OcrFieldExtraction:
        config = configuration or self._configuration or default_extraction_configuration()
        out = OcrFieldExtraction()
        code_aliases, qty_aliases = self._resolve_aliases(config)
        lines = self._lines_from_blocks(read.text_blocks)
        if not lines and read.full_text.strip():
            lines = [(ln, None, None, None, None) for ln in read.full_text.splitlines() if ln.strip()]

        tokens = self._normalizer.normalize_blocks(read.text_blocks)
        if not tokens and read.full_text.strip():
            # Synthetic tokens from full_text lines when blocks are empty.
            synthetic = tuple(
                OcrTextBlock(
                    text=ln,
                    confidence=None,
                    left=None,
                    top=None,
                    width=None,
                    height=None,
                )
                for ln in read.full_text.splitlines()
                if ln.strip()
            )
            tokens = self._normalizer.normalize_blocks(synthetic)

        out.stats["raw_text_block_count"] = len(read.text_blocks or ())
        out.stats["normalized_token_count"] = len(tokens)

        # Detect anchors (profile primary + code/qty aliases).
        configured_anchors_list = list(config.label_detection_rules.primary_anchors) + list(
            config.label_detection_rules.secondary_anchors
        )
        for src in config.internal_code_sources:
            configured_anchors_list.extend(src.aliases)
        configured_anchors_list.extend(config.quantity_rules.aliases)
        configured_anchors: tuple[str, ...] = tuple(
            dict.fromkeys(a for a in configured_anchors_list if a)
        )
        line_texts: list[tuple[str, NormalizedOcrToken | None]] = [
            (text, None) for text, *_rest in lines
        ]
        anchor_matches = self._anchor_matcher.match_anchors(
            configured_anchors=configured_anchors,
            tokens=tokens,
            line_texts=line_texts,
        )
        out.matched_anchors = [
            {
                "configured_anchor": m.configured_anchor,
                "matched_text": m.matched_text,
                "mode": m.mode,
                "similarity": m.similarity,
            }
            for m in anchor_matches
        ]
        out.stats["configured_anchor_count"] = len(configured_anchors)
        out.stats["matched_anchor_count"] = len(anchor_matches)
        out.stats["exact_match_count"] = sum(
            1 for m in anchor_matches if m.mode in ("EXACT", "NORMALIZED")
        )
        out.stats["fuzzy_match_count"] = sum(1 for m in anchor_matches if m.mode == "FUZZY")

        for text, conf, region, _block_num, _line_num in lines:
            self._extract_labeled_line(text, conf, region, out, code_aliases, qty_aliases)

        # Spatial: value on the line immediately below a lone label (exact or fuzzy).
        label_alias_set = code_aliases | qty_aliases | set(_ARTICLE_ALIASES)
        for idx, (text, conf, region, block_num, line_num) in enumerate(lines):
            folded = _fold(text).rstrip(":")
            matched_alias = self._match_alias(folded, label_alias_set)
            if matched_alias is None:
                continue
            if idx + 1 >= len(lines):
                continue
            nxt, nconf, nregion, nblock_num, nline_num = lines[idx + 1]
            if ":" in nxt:
                continue
            nxt_folded = _fold(nxt).rstrip(":")
            if self._match_alias(nxt_folded, label_alias_set) is not None:
                continue
            if block_num is not None and nblock_num is not None and block_num != nblock_num:
                continue
            if not _horizontal_overlap(region, nregion):
                continue
            method = "LABELED_FUZZY" if matched_alias != folded else "LABELED_EXACT"
            self._assign_by_label(
                matched_alias,
                nxt.strip(),
                nconf or conf,
                nregion or region,
                out,
                "below_label",
                code_aliases=code_aliases,
                qty_aliases=qty_aliases,
                extraction_method=method,
                anchor_text=text,
                anchor_bbox=region,
                line_num=nline_num,
                block_num=nblock_num,
            )

        if not out.ean_candidates:
            self._scan_bare_eans(lines, out)

        # Second path: profile-driven numeric tokens (gated — avoids flooding defaults).
        code_before = len(out.internal_code_candidates)
        qty_before = len(out.quantity_candidates)
        policy = config.validation_rules.code.unanchored_candidate_policy
        should_scan_numeric = (
            config.validation_rules.code.exact_length is not None
            or policy is not UnanchoredCodeCandidatePolicy.REJECT
        )
        numeric_accepted: list[dict[str, Any]] = []
        if should_scan_numeric:
            numeric = self._numeric_generator.generate(
                tokens,
                rules=config.validation_rules.code,
            )
            out.stats["raw_numeric_token_count"] = numeric.raw_numeric_token_count
            out.stats["raw_alphanumeric_token_count"] = numeric.raw_alphanumeric_token_count
            out.stats["code_candidates_before_filter"] = code_before + numeric.before_filter
            for rej in numeric.rejected:
                out.rejected_candidates.append(
                    {
                        "field": "internal_code",
                        "masked_value": rej.masked_value,
                        "length": rej.length,
                        "reason_code": rej.reason_code,
                        "source": rej.source,
                        "confidence": rej.confidence,
                    }
                )
            numeric_accepted = list(numeric.accepted)
        else:
            out.stats["raw_numeric_token_count"] = 0
            out.stats["raw_alphanumeric_token_count"] = 0
            out.stats["code_candidates_before_filter"] = code_before
        out.stats["quantity_candidates_before_filter"] = qty_before
        existing_values = {
            c.value.strip() for c in out.internal_code_candidates if c.value
        }
        for item in numeric_accepted:
            value = str(item["value"])
            if value in existing_values:
                continue
            if policy is UnanchoredCodeCandidatePolicy.REJECT and not anchor_matches:
                out.rejected_candidates.append(
                    {
                        "field": "internal_code",
                        "masked_value": mask_value(value),
                        "length": len(value),
                        "reason_code": "CODE_UNANCHORED_NOT_ALLOWED",
                        "source": "NUMERIC_PATTERN",
                    }
                )
                continue
            # Attach best spatial relation to a code/qty anchor when possible.
            relation = None
            distance = None
            anchor_text = None
            anchor_bbox = None
            value_bbox = _to_bbox(item.get("bounding_box"))
            best_anchor = None
            for am in anchor_matches:
                ab = _to_bbox(am.bounding_box)
                if value_bbox is None or ab is None:
                    continue
                source_rule = next(
                    (
                        s
                        for s in config.internal_code_sources
                        if s.field_key.upper() == "INTERNAL_CODE"
                    ),
                    None,
                )
                allowed = (
                    source_rule.allowed_spatial_relations
                    if source_rule and source_rule.allowed_spatial_relations
                    else ("BELOW", "SAME_COLUMN", "NEAR", "RIGHT_OF")
                )
                eval_res = self._spatial.evaluate(
                    anchor=ab,
                    value=value_bbox,
                    allowed=allowed,
                    maximum_anchor_distance_ratio=(
                        source_rule.maximum_anchor_distance_ratio if source_rule else 0.35
                    ),
                )
                if best_anchor is None or eval_res.normalized_distance < best_anchor[2]:
                    best_anchor = (am, eval_res, eval_res.normalized_distance)
            if best_anchor is not None:
                am, eval_res, _ = best_anchor
                relation = eval_res.relation
                distance = eval_res.normalized_distance
                anchor_text = am.configured_anchor
                anchor_bbox = am.bounding_box
                method = (
                    "LABELED_FUZZY"
                    if am.mode == "FUZZY"
                    else "LABELED_EXACT"
                    if eval_res.matches_allowed
                    else "NUMERIC_PATTERN"
                )
            else:
                method = "NUMERIC_PATTERN"

            conf = item.get("confidence")
            score_conf = float(conf) if conf is not None else 0.55
            if method == "NUMERIC_PATTERN":
                score_conf = min(score_conf, 0.65) * 0.85

            out.internal_code_candidates.append(
                OcrFieldCandidate(
                    kind=OcrFieldKind.INTERNAL_CODE,
                    value=value,
                    source="numeric_pattern",
                    associated_text=str(item.get("neighbor_text") or value),
                    confidence=score_conf,
                    region=item.get("bounding_box"),
                    rule="numeric_pattern",
                    extraction_method=method,
                    anchor_text=anchor_text,
                    anchor_bbox=anchor_bbox,
                    spatial_relation=relation,
                    normalized_distance=distance,
                    neighbor_text=item.get("neighbor_text"),
                    line_num=item.get("line_num"),
                    block_num=item.get("block_num"),
                )
            )
            existing_values.add(value)

        out.stats["code_candidates_after_filter"] = len(out.internal_code_candidates)
        out.stats["quantity_candidates_after_filter"] = len(out.quantity_candidates)
        out.stats["rejected_candidate_count"] = len(out.rejected_candidates)
        rejection_reasons: dict[str, int] = {}
        for rejected_entry in out.rejected_candidates:
            reason = str(rejected_entry.get("reason_code") or "UNKNOWN")
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        out.stats["rejection_reasons"] = rejection_reasons
        return out

    def _resolve_aliases(
        self, config: ExtractionProfileConfiguration
    ) -> tuple[set[str], set[str]]:
        code: set[str] = {_fold(a) for a in _CODE_ALIASES}
        qty: set[str] = {_fold(a) for a in _QTY_ALIASES}
        for src in config.internal_code_sources:
            if not src.enabled:
                continue
            for alias in src.aliases:
                code.add(_fold(alias))
        for alias in config.quantity_rules.aliases:
            qty.add(_fold(alias))
        for alias in config.aliases.get("quantity", ()):
            qty.add(_fold(alias))
        for alias in config.aliases.get("internal_code", ()):
            code.add(_fold(alias))
        return code, qty

    def _match_alias(self, folded: str, aliases: set[str]) -> str | None:
        if folded in aliases:
            return folded
        # Limited fuzzy: allow near-miss for multi-word aliases.
        matcher = OcrAnchorMatcher(mode=AnchorMatchMode.FUZZY, similarity_threshold=0.82)
        from src.application.services.image_processing.ocr_token_normalizer import (
            NormalizedOcrToken,
        )

        tok = NormalizedOcrToken(
            original_text=folded,
            normalized_text=folded,
            confidence=None,
            bounding_box=None,
            line_num=None,
            block_num=None,
        )
        hits = matcher.match_anchors(configured_anchors=tuple(aliases), tokens=[tok])
        if hits:
            return _fold(hits[0].configured_anchor)
        return None

    def _lines_from_blocks(
        self, blocks: tuple[OcrTextBlock, ...]
    ) -> list[tuple[str, float | None, tuple[int, int, int, int] | None, int | None, int | None]]:
        if not blocks:
            return []
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

        lines: list[
            tuple[str, float | None, tuple[int, int, int, int] | None, int | None, int | None]
        ] = []
        for key in sorted(grouped.keys()):
            parts = sorted(grouped[key], key=lambda x: (x.left or 0))
            text = " ".join((p.text or "").strip() for p in parts if (p.text or "").strip())
            confs = [p.confidence for p in parts if p.confidence is not None]
            conf = sum(confs) / len(confs) if confs else None
            region = _region(parts[0])
            block_num = key[0]
            line_num = key[1]
            if text:
                for sub in text.splitlines():
                    sub = sub.strip()
                    if sub:
                        lines.append((sub, conf, region, block_num, line_num))
        for b in singles:
            for sub in (b.text or "").splitlines():
                sub = sub.strip()
                if sub:
                    lines.append((sub, b.confidence, _region(b), b.block_num, b.line_num))
        return lines

    def _extract_labeled_line(
        self,
        text: str,
        conf: float | None,
        region: tuple[int, int, int, int] | None,
        out: OcrFieldExtraction,
        code_aliases: set[str],
        qty_aliases: set[str],
    ) -> None:
        m = _LABEL_VALUE.match(text.strip())
        if not m:
            return
        label = _fold(m.group("label"))
        value = m.group("value").strip()
        matched = self._match_alias(label, code_aliases | qty_aliases | set(_ARTICLE_ALIASES))
        if matched is None:
            return
        method = "LABELED_FUZZY" if matched != label else "LABELED_EXACT"
        self._assign_by_label(
            matched,
            value,
            conf,
            region,
            out,
            "labeled_same_line",
            code_aliases=code_aliases,
            qty_aliases=qty_aliases,
            extraction_method=method,
            anchor_text=m.group("label"),
            anchor_bbox=region,
        )

    def _assign_by_label(
        self,
        label: str,
        value: str,
        conf: float | None,
        region: tuple[int, int, int, int] | None,
        out: OcrFieldExtraction,
        rule: str,
        *,
        code_aliases: set[str],
        qty_aliases: set[str],
        extraction_method: str = "LABELED_EXACT",
        anchor_text: str | None = None,
        anchor_bbox: tuple[int, int, int, int] | None = None,
        line_num: int | None = None,
        block_num: int | None = None,
    ) -> None:
        value = value.strip()
        if not value:
            return
        def _candidate(
            kind: OcrFieldKind,
            source: str,
            associated_text: str,
        ) -> OcrFieldCandidate:
            return OcrFieldCandidate(
                kind=kind,
                value=value,
                source=source,
                associated_text=associated_text,
                confidence=conf,
                region=region,
                rule=rule,
                extraction_method=extraction_method,
                anchor_text=anchor_text or label,
                anchor_bbox=anchor_bbox or region,
                line_num=line_num,
                block_num=block_num,
            )

        if label in qty_aliases:
            out.quantity_candidates.append(
                _candidate(OcrFieldKind.QUANTITY, "label", label)
            )
            return
        if label == "ean" or label.startswith("ean"):
            out.ean_candidates.append(
                _candidate(OcrFieldKind.EAN, "label", label)
            )
            out.internal_code_candidates.append(
                _candidate(OcrFieldKind.INTERNAL_CODE, "ean_label", label)
            )
            return
        if label in code_aliases:
            out.internal_code_candidates.append(
                _candidate(OcrFieldKind.INTERNAL_CODE, "label", label)
            )
            return
        if label in ("articulo", "artículo", "art", "art."):
            out.article_candidates.append(
                _candidate(OcrFieldKind.ARTICLE, "label", label)
            )
            out.internal_code_candidates.append(
                _candidate(OcrFieldKind.INTERNAL_CODE, "article_label", label)
            )
            return
        if label in ("producto", "product"):
            out.product_candidates.append(
                _candidate(OcrFieldKind.PRODUCT, "label", label)
            )
            out.internal_code_candidates.append(
                _candidate(OcrFieldKind.INTERNAL_CODE, "product_label", label)
            )
            return
        if label in _LOT_ALIASES:
            out.lot_candidates.append(
                _candidate(OcrFieldKind.LOT, "label", label)
            )
            return
        if label in _EXP_ALIASES:
            out.expiration_candidates.append(
                _candidate(OcrFieldKind.EXPIRATION, "label", label)
            )
            return
        if label in _RECEPTION_ALIASES:
            out.reception_candidates.append(
                _candidate(OcrFieldKind.RECEPTION, "label", label)
            )
            return
        if label in _RESPONSIBLE_ALIASES:
            out.responsible_candidates.append(
                _candidate(OcrFieldKind.RESPONSIBLE, "label", label)
            )

    def _scan_bare_eans(
        self,
        lines: list[
            tuple[str, float | None, tuple[int, int, int, int] | None, int | None, int | None]
        ],
        out: OcrFieldExtraction,
    ) -> None:
        for text, conf, region, block_num, line_num in lines:
            for token in re.split(r"\s+", text.strip()):
                if _EAN_PATTERN.fullmatch(token):
                    out.ean_candidates.append(
                        OcrFieldCandidate(
                            OcrFieldKind.EAN,
                            token,
                            "bare_ean",
                            text,
                            conf,
                            region,
                            "bare_ean",
                            extraction_method="BARCODE",
                            line_num=line_num,
                            block_num=block_num,
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
                            extraction_method="BARCODE",
                            line_num=line_num,
                            block_num=block_num,
                        )
                    )


__all__ = [
    "OcrFieldCandidate",
    "OcrFieldExtraction",
    "OcrFieldExtractor",
    "OcrFieldKind",
]
