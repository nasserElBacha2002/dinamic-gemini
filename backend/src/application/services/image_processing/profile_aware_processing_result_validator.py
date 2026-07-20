"""Phase 6 — profile-aware shared validation for CODE_SCAN / OCR / EXTERNAL."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    default_extraction_configuration,
)


class ExtractionValidationErrorCode(str, Enum):
    MISSING_INTERNAL_CODE = "MISSING_INTERNAL_CODE"
    MISSING_QUANTITY = "MISSING_QUANTITY"
    INVALID_INTERNAL_CODE = "INVALID_INTERNAL_CODE"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    AMBIGUOUS_INTERNAL_CODE = "AMBIGUOUS_INTERNAL_CODE"
    AMBIGUOUS_QUANTITY = "AMBIGUOUS_QUANTITY"
    REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
    UNSUPPORTED_BARCODE_FORMAT = "UNSUPPORTED_BARCODE_FORMAT"
    INVALID_EAN_CHECKSUM = "INVALID_EAN_CHECKSUM"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    PROFILE_INVALID = "PROFILE_INVALID"


@dataclass(frozen=True)
class FieldCandidate:
    source_key: str
    value: str
    evidence_score: float = 1.0


@dataclass
class ProfileValidationResult:
    ok: bool
    internal_code: str | None = None
    quantity: int | None = None
    internal_code_source: str | None = None
    quantity_source: str | None = None
    additional_fields: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_alias_key(text: str) -> str:
    """Trim, casefold, accent-insensitive, collapse spaces."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = re.sub(r"\s+", " ", without_marks.strip())
    collapsed = re.sub(r"[^\w\s./\-]", "", collapsed, flags=re.UNICODE)
    return collapsed.casefold().strip()


def ean_checksum_valid(digits: str) -> bool:
    if not digits.isdigit():
        return False
    n = len(digits)
    if n not in (8, 12, 13, 14):
        return False
    body, check = digits[:-1], int(digits[-1])
    total = 0
    # GS1: from the right, odd positions *3
    for i, ch in enumerate(reversed(body)):
        weight = 3 if (i % 2 == 0) else 1
        total += int(ch) * weight
    return (10 - (total % 10)) % 10 == check


class ProfileAwareProcessingResultValidator:
    """Shared deterministic validator driven by ExtractionProfileConfiguration."""

    def __init__(self, configuration: ExtractionProfileConfiguration | None = None) -> None:
        self._config = configuration or default_extraction_configuration()

    @property
    def configuration(self) -> ExtractionProfileConfiguration:
        return self._config

    def validate_resolved(
        self,
        *,
        code_candidates: list[FieldCandidate],
        quantity_candidates: list[FieldCandidate],
        barcode_format: str | None = None,
        additional: dict[str, str] | None = None,
    ) -> ProfileValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if barcode_format:
            fmt = barcode_format.strip().upper()
            if fmt and fmt not in self._config.accepted_barcode_formats:
                errors.append(ExtractionValidationErrorCode.UNSUPPORTED_BARCODE_FORMAT.value)
                return ProfileValidationResult(ok=False, errors=errors)

        code, code_source, code_errors = self._resolve_internal_code(code_candidates)
        errors.extend(code_errors)
        qty, qty_source, qty_errors = self._resolve_quantity(quantity_candidates)
        errors.extend(qty_errors)

        for req in self._config.required_fields:
            if req == "internal_code" and not code:
                if ExtractionValidationErrorCode.MISSING_INTERNAL_CODE.value not in errors:
                    errors.append(ExtractionValidationErrorCode.MISSING_INTERNAL_CODE.value)
            if req == "quantity" and qty is None:
                if ExtractionValidationErrorCode.MISSING_QUANTITY.value not in errors:
                    errors.append(ExtractionValidationErrorCode.MISSING_QUANTITY.value)

        add_out = dict(additional or {})
        for field_rule in self._config.additional_fields:
            if field_rule.required and field_rule.field_key not in add_out:
                errors.append(ExtractionValidationErrorCode.REQUIRED_FIELD_MISSING.value)
                warnings.append(f"missing_required:{field_rule.field_key}")

        ok = not errors and bool(code) and qty is not None and qty > 0
        return ProfileValidationResult(
            ok=ok,
            internal_code=code,
            quantity=qty,
            internal_code_source=code_source,
            quantity_source=qty_source,
            additional_fields=add_out,
            errors=errors,
            warnings=warnings,
        )

    def _resolve_internal_code(
        self, candidates: list[FieldCandidate]
    ) -> tuple[str | None, str | None, list[str]]:
        if not candidates:
            return None, None, []
        forbidden = {s.upper() for s in self._config.forbidden_internal_code_sources}
        by_source: dict[str, list[FieldCandidate]] = {}
        for c in candidates:
            key = c.source_key.strip().upper()
            if key in forbidden:
                continue
            by_source.setdefault(key, []).append(c)

        ordered = [
            s
            for s in sorted(self._config.internal_code_sources, key=lambda x: x.priority)
            if s.enabled and s.allowed_as_internal_code
        ]
        for source in ordered:
            key = source.field_key.upper()
            opts = by_source.get(key) or []
            if not opts:
                continue
            # Ambiguity: two comparable candidates for same source.
            distinct = {self._normalize_code(o.value) for o in opts if o.value}
            distinct.discard("")
            if len(distinct) > 1:
                scores = {o.evidence_score for o in opts}
                if len(scores) <= 1 or max(scores) - min(scores) < 0.05:
                    return None, None, [ExtractionValidationErrorCode.AMBIGUOUS_INTERNAL_CODE.value]
            chosen = max(opts, key=lambda o: o.evidence_score)
            code = self._normalize_code(chosen.value)
            err = self._validate_code_value(code, source_key=key)
            if err:
                return None, None, [err]
            return code, key, []
        # Fallback: first candidate if no structured sources matched
        if candidates:
            c = max(candidates, key=lambda o: o.evidence_score)
            code = self._normalize_code(c.value)
            err = self._validate_code_value(code, source_key=c.source_key.upper())
            if err:
                return None, None, [err]
            return code or None, c.source_key.upper(), []
        return None, None, []

    def _resolve_quantity(
        self, candidates: list[FieldCandidate]
    ) -> tuple[int | None, str | None, list[str]]:
        rules = self._config.quantity_rules
        if not candidates:
            return None, None, []
        parsed: list[tuple[int, FieldCandidate]] = []
        for c in candidates:
            q = self._parse_quantity(c.value)
            if q is None:
                continue
            parsed.append((q, c))
        if not parsed:
            return None, None, [ExtractionValidationErrorCode.INVALID_QUANTITY.value]
        values = {q for q, _ in parsed}
        if len(values) > 1:
            return None, None, [ExtractionValidationErrorCode.AMBIGUOUS_QUANTITY.value]
        q, c = max(parsed, key=lambda t: t[1].evidence_score)
        if q < rules.minimum or q > rules.maximum:
            return None, None, [ExtractionValidationErrorCode.INVALID_QUANTITY.value]
        if rules.allow_negative is False and q < 0:
            return None, None, [ExtractionValidationErrorCode.INVALID_QUANTITY.value]
        return q, c.source_key, []

    def _normalize_code(self, value: str) -> str:
        text = (value or "").strip()
        if not self._config.validation_rules.code.preserve_leading_zeros:
            text = text.lstrip("0") or "0"
        if not self._config.validation_rules.code.allow_spaces:
            text = text.replace(" ", "")
        return text

    def _validate_code_value(self, code: str, *, source_key: str) -> str | None:
        rules = self._config.validation_rules.code
        if not code:
            return ExtractionValidationErrorCode.MISSING_INTERNAL_CODE.value
        if len(code) < rules.min_length or len(code) > rules.max_length:
            return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
        for ch in code:
            if ch.isalpha() and not rules.allow_letters:
                return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
            if ch.isdigit() and not rules.allow_digits:
                return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
            if ch == "-" and not rules.allow_hyphen:
                return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
            if ch == "/" and not rules.allow_slash:
                return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
            if ch == " " and not rules.allow_spaces:
                return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
        if rules.regex:
            if re.fullmatch(rules.regex, code) is None:
                return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
        if source_key == "EAN":
            ean = self._config.validation_rules.ean
            n = len(code)
            if code.isdigit():
                if n == 8 and not ean.allow_ean8:
                    return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
                if n == 12 and not ean.allow_ean12:
                    return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
                if n == 13 and not ean.allow_ean13:
                    return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
                if n == 14 and not ean.allow_ean14:
                    return ExtractionValidationErrorCode.INVALID_INTERNAL_CODE.value
                if ean.validate_checksum and n in (8, 12, 13, 14):
                    if not ean_checksum_valid(code):
                        return ExtractionValidationErrorCode.INVALID_EAN_CHECKSUM.value
        return None

    def _parse_quantity(self, raw: str) -> int | None:
        text = (raw or "").strip().replace(",", ".")
        if not text:
            return None
        try:
            if self._config.validation_rules.quantity_integer_only or not self._config.quantity_rules.allow_decimals:
                if "." in text:
                    return None
                value = int(text)
            else:
                value = int(float(text))
        except ValueError:
            return None
        return value


def configuration_to_ocr_client_field_rules(config: ExtractionProfileConfiguration):
    """Bridge profile → legacy OcrClientFieldRules for INTERNAL_OCR until fully migrated."""
    from src.application.services.image_processing.ocr_result_normalizer import OcrClientFieldRules

    mapping = {
        "EAN": ("ean_label", "bare_ean"),
        "INTERNAL_CODE": ("label",),
        "ARTICLE": ("article_label",),
        "SKU": ("label",),
        "PRODUCT": ("product_label",),
    }
    priority: list[str] = []
    for src in sorted(config.internal_code_sources, key=lambda s: s.priority):
        if not src.enabled or not src.allowed_as_internal_code:
            continue
        for tag in mapping.get(src.field_key.upper(), ()):
            if tag not in priority:
                priority.append(tag)
    prefer_ean = bool(priority and priority[0] in ("ean_label", "bare_ean"))
    return OcrClientFieldRules(
        profile_key="supplier_extraction_profile",
        profile_version="1",
        internal_code_priority=tuple(priority)
        or OcrClientFieldRules().internal_code_priority,
        prefer_ean_as_internal_code=prefer_ean,
        required_fields=tuple(config.required_fields) or ("internal_code", "quantity"),
    )


def snapshot_dict_from_configuration(
    *,
    profile_id: str | None,
    profile_key: str,
    profile_version: int,
    client_id: str | None,
    supplier_id: str | None,
    configuration: ExtractionProfileConfiguration,
    visual_notes_version: int | None = None,
    snapshot_version: int = 1,
) -> dict[str, Any]:
    return {
        "supplier_profile_id": profile_id,
        "supplier_profile_key": profile_key,
        "supplier_profile_version": profile_version,
        "client_id": client_id,
        "supplier_id": supplier_id,
        "internal_code_priority": [
            s.field_key for s in sorted(configuration.internal_code_sources, key=lambda x: x.priority)
            if s.enabled
        ],
        "quantity_rules": configuration.to_public_dict()["quantity_rules"],
        "required_fields": list(configuration.required_fields),
        "additional_fields": configuration.to_public_dict()["additional_fields"],
        "validation_rules": configuration.to_public_dict()["validation_rules"],
        "accepted_code_formats": list(configuration.accepted_barcode_formats),
        "qr_payload_rules": list(configuration.qr_payload_formats),
        "aliases": configuration.to_public_dict()["aliases"],
        "forbidden_internal_code_sources": list(configuration.forbidden_internal_code_sources),
        "visual_notes_version": visual_notes_version,
        "snapshot_version": snapshot_version,
        "configuration": configuration.to_public_dict(),
    }


__all__ = [
    "ExtractionValidationErrorCode",
    "FieldCandidate",
    "ProfileAwareProcessingResultValidator",
    "ProfileValidationResult",
    "configuration_to_ocr_client_field_rules",
    "ean_checksum_valid",
    "normalize_alias_key",
    "snapshot_dict_from_configuration",
]
