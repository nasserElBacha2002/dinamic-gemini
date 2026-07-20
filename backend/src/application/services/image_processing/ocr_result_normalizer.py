"""Phase 4 — normalize OCR field candidates into a single validated label result.

Applies client field-priority rules (e.g. prefer EAN as internal_code) without hardcoding
client names in the orchestrator. Ambiguity is never resolved silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from src.application.services.image_processing.encoded_label_payload_parser import (
    CODE_MAX_LENGTH,
)
from src.application.services.image_processing.ocr_field_extractor import (
    OcrFieldCandidate,
    OcrFieldExtraction,
)

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# Safe OCR digit confusions only inside strictly numeric fields.
_NUMERIC_OCR_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "s": "5"})
_CODE_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]*$")


class OcrNormalizeStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNRECOGNIZED = "UNRECOGNIZED"
    PENDING_MANUAL_REVIEW = "PENDING_MANUAL_REVIEW"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class OcrClientFieldRules:
    """Per-client / default priorities for choosing internal_code among labeled fields.

    ``internal_code_priority`` is an ordered list of source tags, e.g.
    ``("ean_label", "label", "article_label", "product_label", "bare_ean")``.
    Clients that historically map EAN → internal_code put ``ean_label`` / ``bare_ean`` first
    (configured via settings client-id lists, never hardcoded client names here).
    """

    profile_key: str = "default"
    profile_version: str = "1"
    internal_code_priority: tuple[str, ...] = (
        "label",
        "article_label",
        "product_label",
        "ean_label",
        "bare_ean",
    )
    prefer_ean_as_internal_code: bool = False
    required_fields: tuple[str, ...] = ("internal_code", "quantity")


@dataclass
class NormalizedOcrLabel:
    status: OcrNormalizeStatus
    internal_code: str | None = None
    quantity: int | None = None
    additional_fields: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    selected_code_rule: str | None = None
    selected_qty_rule: str | None = None


class OcrResultNormalizer:
    def __init__(
        self,
        *,
        quantity_max: int,
        code_max_length: int = CODE_MAX_LENGTH,
        client_rules: OcrClientFieldRules | None = None,
    ) -> None:
        self._quantity_max = int(quantity_max)
        self._code_max_length = int(code_max_length)
        self._rules = client_rules or OcrClientFieldRules()

    def normalize(self, extraction: OcrFieldExtraction) -> NormalizedOcrLabel:
        warnings = list(extraction.warnings)
        additional = self._additional(extraction)

        code, code_warns, code_rule = self._pick_internal_code(extraction.internal_code_candidates)
        warnings.extend(code_warns)
        qty, qty_warns, qty_rule = self._pick_quantity(extraction.quantity_candidates)
        warnings.extend(qty_warns)

        if "AMBIGUOUS_INTERNAL_CODE" in warnings or "AMBIGUOUS_QUANTITY" in warnings:
            return NormalizedOcrLabel(
                status=OcrNormalizeStatus.AMBIGUOUS,
                internal_code=code,
                quantity=qty,
                additional_fields=additional,
                warnings=warnings,
                validation_errors=[
                    w
                    for w in warnings
                    if w in ("AMBIGUOUS_INTERNAL_CODE", "AMBIGUOUS_QUANTITY")
                ],
                selected_code_rule=code_rule,
                selected_qty_rule=qty_rule,
            )

        if code and qty is not None:
            return NormalizedOcrLabel(
                status=OcrNormalizeStatus.RESOLVED,
                internal_code=code,
                quantity=qty,
                additional_fields=additional,
                warnings=warnings,
                selected_code_rule=code_rule,
                selected_qty_rule=qty_rule,
            )

        if code and qty is None:
            return NormalizedOcrLabel(
                status=OcrNormalizeStatus.PENDING_MANUAL_REVIEW,
                internal_code=code,
                additional_fields=additional,
                warnings=warnings + ["QUANTITY_MISSING"],
                validation_errors=["QUANTITY_MISSING"],
                selected_code_rule=code_rule,
            )

        if not code and qty is not None:
            return NormalizedOcrLabel(
                status=OcrNormalizeStatus.PENDING_MANUAL_REVIEW,
                quantity=qty,
                additional_fields=additional,
                warnings=warnings + ["NO_INTERNAL_CODE"],
                validation_errors=["NO_INTERNAL_CODE"],
                selected_qty_rule=qty_rule,
            )

        return NormalizedOcrLabel(
            status=OcrNormalizeStatus.UNRECOGNIZED,
            additional_fields=additional,
            warnings=warnings + ["NO_INTERNAL_CODE", "QUANTITY_MISSING"],
            validation_errors=["NO_INTERNAL_CODE", "QUANTITY_MISSING"],
        )

    def _additional(self, extraction: OcrFieldExtraction) -> dict[str, str]:
        out: dict[str, str] = {}
        mapping = (
            ("ean", extraction.ean_candidates),
            ("articulo", extraction.article_candidates),
            ("producto", extraction.product_candidates),
            ("lote", extraction.lot_candidates),
            ("vencimiento", extraction.expiration_candidates),
            ("recepcion", extraction.reception_candidates),
            ("responsable", extraction.responsible_candidates),
        )
        for key, cands in mapping:
            if cands:
                cleaned = self._clean_text(cands[0].value, numeric_only=False)
                if cleaned:
                    out[key] = cleaned
        return out

    def _pick_internal_code(
        self, candidates: list[OcrFieldCandidate]
    ) -> tuple[str | None, list[str], str | None]:
        warnings: list[str] = []
        if not candidates:
            return None, warnings, None

        priority = list(self._rules.internal_code_priority)
        if self._rules.prefer_ean_as_internal_code:
            # Ensure EAN sources win when present.
            for tag in ("ean_label", "bare_ean"):
                if tag in priority:
                    priority.remove(tag)
                    priority.insert(0, tag)

        scored: list[tuple[int, OcrFieldCandidate, str]] = []
        for cand in candidates:
            cleaned = self._normalize_code(cand.value)
            if cleaned is None:
                continue
            try:
                rank = priority.index(cand.source)
            except ValueError:
                rank = len(priority)
            scored.append((rank, cand, cleaned))

        if not scored:
            warnings.append("NO_VALID_INTERNAL_CODE_CANDIDATE")
            return None, warnings, None

        scored.sort(key=lambda t: (t[0], t[2]))
        best_rank = scored[0][0]
        top = [s for s in scored if s[0] == best_rank]
        distinct = {s[2] for s in top}
        if len(distinct) > 1:
            warnings.append("AMBIGUOUS_INTERNAL_CODE")
            return None, warnings, None
        _, cand, value = top[0]
        return value, warnings, f"{cand.source}:{cand.rule}"

    def _pick_quantity(
        self, candidates: list[OcrFieldCandidate]
    ) -> tuple[int | None, list[str], str | None]:
        warnings: list[str] = []
        if not candidates:
            return None, warnings, None

        values: list[tuple[int, OcrFieldCandidate]] = []
        for cand in candidates:
            qty = self._normalize_quantity(cand.value)
            if qty is None:
                continue
            values.append((qty, cand))

        if not values:
            warnings.append("QUANTITY_INVALID")
            return None, warnings, None

        distinct = {v[0] for v in values}
        if len(distinct) > 1:
            warnings.append("AMBIGUOUS_QUANTITY")
            return None, warnings, None
        qty, cand = values[0]
        return qty, warnings, f"{cand.source}:{cand.rule}"

    def _normalize_code(self, raw: str) -> str | None:
        text = self._clean_text(raw, numeric_only=False)
        if not text:
            return None
        # Numeric-looking codes (EAN): apply safe OCR digit fixes.
        if text.replace(" ", "").isalnum() and sum(ch.isdigit() for ch in text) >= len(text) * 0.8:
            text = text.translate(_NUMERIC_OCR_FIX)
        text = text.strip()
        if _CONTROL.search(text):
            return None
        if len(text) < 1 or len(text) > self._code_max_length:
            return None
        if not _CODE_OK.fullmatch(text):
            return None
        return text

    def _normalize_quantity(self, raw: str) -> int | None:
        text = self._clean_text(raw, numeric_only=True)
        if not text:
            return None
        text = text.translate(_NUMERIC_OCR_FIX)
        if "." in text or "," in text:
            return None
        try:
            qty = int(text)
        except ValueError:
            return None
        if qty <= 0 or qty > self._quantity_max:
            return None
        return qty

    def _clean_text(self, raw: str, *, numeric_only: bool) -> str:
        text = (raw or "").strip()
        text = re.sub(r"\s+", " ", text)
        if numeric_only:
            # Keep digits and separators only for quantity parsing decision.
            text = re.sub(r"[^\d.,\-]", "", text)
        return text.strip()


__all__ = [
    "NormalizedOcrLabel",
    "OcrClientFieldRules",
    "OcrNormalizeStatus",
    "OcrResultNormalizer",
]
