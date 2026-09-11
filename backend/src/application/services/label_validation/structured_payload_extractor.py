"""Structured barcode/QR payload extraction (recognition ≠ validation).

Reusable by CODE_SCAN, TXT, CSV, and future Vision textual results.
Does not validate issued registry, persist, or know tenants/suppliers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.application.services.label_validation.gs1_payload_parser import Gs1PayloadParser
from src.domain.client_supplier.extraction_profile import (
    ITEM_FIELD_TARGETS,
    POSITION_FIELD_TARGETS,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    FieldMappingSource,
    PayloadStructure,
)
from src.domain.label_profiles.kinds import LabelKind
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    RecognitionSource,
)

_MAX_PAYLOAD_LEN = 512
_MAX_SEGMENTS = 32
_MAX_DELIMITER_LEN = 8


@dataclass(frozen=True)
class StructuredExtractionResult:
    """Outcome of structured extraction (may be unsuccessful without raising)."""

    raw_payload: str
    normalized_payload: str
    candidate: CandidateLabel | None = None
    error_code: str | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.candidate is not None and self.error_code is None


class StructuredPayloadExtractor:
    """raw payload + profile configuration → structured CandidateLabel."""

    def __init__(self, *, gs1_parser: Gs1PayloadParser | None = None) -> None:
        self._gs1 = gs1_parser or Gs1PayloadParser()

    def extract(
        self,
        *,
        raw_payload: str,
        configuration: ExtractionProfileConfiguration,
        label_kind: LabelKind,
        symbology: str | None = None,
        recognition_source: RecognitionSource = RecognitionSource.CODE_SCAN,
    ) -> StructuredExtractionResult:
        raw = raw_payload if raw_payload is not None else ""
        if len(raw) > _MAX_PAYLOAD_LEN:
            return StructuredExtractionResult(
                raw_payload=raw,
                normalized_payload=raw,
                error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                detail="payload exceeds extraction length limit",
            )

        rules = configuration.effective_deterministic()
        if rules.payload_structure is PayloadStructure.GS1:
            return self._extract_gs1(
                raw=raw,
                configuration=configuration,
                rules=rules,
                label_kind=label_kind,
                symbology=symbology,
                recognition_source=recognition_source,
            )

        if rules.payload_structure is PayloadStructure.SEGMENTED:
            return self._extract_segmented(
                raw=raw,
                configuration=configuration,
                rules=rules,
                label_kind=label_kind,
                symbology=symbology,
                recognition_source=recognition_source,
            )

        # SIMPLE: full identity normalization applies to the whole payload.
        normalized = self.normalize(raw, rules)
        try:
            fields = self._map_fields(
                normalized=normalized,
                rules=rules,
                label_kind=label_kind,
                schema_version=int(configuration.configuration_schema_version),
                segments=None,
            )
        except StructuredExtractionError as exc:
            return StructuredExtractionResult(
                raw_payload=raw,
                normalized_payload=normalized,
                error_code=exc.code,
                detail=exc.message,
            )

        return self._candidate_from_fields(
            raw=raw,
            normalized=normalized,
            fields=fields,
            label_kind=label_kind,
            symbology=symbology,
            recognition_source=recognition_source,
            extra_meta={
                "payload_structure": PayloadStructure.SIMPLE.value,
                "mapped_fields": ",".join(sorted(k for k, v in fields.items() if v)),
            },
        )

    def _extract_gs1(
        self,
        *,
        raw: str,
        configuration: ExtractionProfileConfiguration,
        rules: DeterministicBarcodeRules,
        label_kind: LabelKind,
        symbology: str | None,
        recognition_source: RecognitionSource,
    ) -> StructuredExtractionResult:
        del configuration
        parsed = self._gs1.parse(raw)
        if not parsed.ok:
            return StructuredExtractionResult(
                raw_payload=raw,
                normalized_payload=parsed.encoded_payload or raw,
                error_code=parsed.error_code
                or LabelValidationErrorCode.LABEL_GS1_INVALID.value,
                detail=parsed.detail,
            )

        by_ai = parsed.by_ai()
        for required in rules.required_application_identifiers:
            ai = str(required).strip()
            if ai not in by_ai:
                return StructuredExtractionResult(
                    raw_payload=raw,
                    normalized_payload=parsed.encoded_payload,
                    error_code=LabelValidationErrorCode.LABEL_GS1_REQUIRED_AI_MISSING.value,
                    detail=f"required Application Identifier {ai} missing",
                )

        try:
            fields = self._map_gs1_fields(
                by_ai=by_ai, rules=rules, label_kind=label_kind
            )
        except StructuredExtractionError as exc:
            return StructuredExtractionResult(
                raw_payload=raw,
                normalized_payload=parsed.encoded_payload,
                error_code=exc.code,
                detail=exc.message,
            )

        ai_meta = {
            f"gs1_ai_{f.ai}": f.normalized_value for f in parsed.fields if f.known
        }
        ai_meta["gs1_application_identifiers"] = ",".join(
            f.ai for f in parsed.fields if f.known
        )
        unknown = [f.ai for f in parsed.fields if not f.known]
        if unknown:
            ai_meta["gs1_unknown_ais"] = ",".join(unknown)

        return self._candidate_from_fields(
            raw=raw,
            normalized=parsed.encoded_payload,
            fields=fields,
            label_kind=label_kind,
            symbology=symbology,
            recognition_source=recognition_source,
            extra_meta={
                **ai_meta,
                "payload_structure": PayloadStructure.GS1.value,
                "mapped_fields": ",".join(sorted(k for k, v in fields.items() if v)),
            },
        )

    def _extract_segmented(
        self,
        *,
        raw: str,
        configuration: ExtractionProfileConfiguration,
        rules: DeterministicBarcodeRules,
        label_kind: LabelKind,
        symbology: str | None,
        recognition_source: RecognitionSource,
    ) -> StructuredExtractionResult:
        """SEGMENTED: structural trim → split → map → per-field identity normalize.

        Identifier normalization (case / hyphens / internal spaces) must not run on the
        full payload before splitting — otherwise delimiter + quantity participate in
        identity shape checks. Quantity segments are strip-only.
        """
        structural = self.normalize_structural(raw, rules)
        delimiter = rules.delimiter or "|"
        if not delimiter or len(delimiter) > _MAX_DELIMITER_LEN:
            return StructuredExtractionResult(
                raw_payload=raw,
                normalized_payload=structural,
                error_code=LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                detail="invalid segmented delimiter",
            )
        delimiter_detected = delimiter in structural
        if (
            rules.expected_segment_count is not None
            and int(rules.expected_segment_count) > 1
            and not delimiter_detected
        ):
            return StructuredExtractionResult(
                raw_payload=raw,
                normalized_payload=structural,
                error_code=LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                detail=(
                    f"delimiter not found in payload; "
                    f"expected {rules.expected_segment_count} segments"
                ),
            )
        segments = structural.split(delimiter)
        segment_count = len(segments)
        if segment_count > _MAX_SEGMENTS:
            return StructuredExtractionResult(
                raw_payload=raw,
                normalized_payload=structural,
                error_code=LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                detail=f"segment count exceeds {_MAX_SEGMENTS}",
            )
        if (
            rules.expected_segment_count is not None
            and segment_count != int(rules.expected_segment_count)
        ):
            return StructuredExtractionResult(
                raw_payload=raw,
                normalized_payload=structural,
                error_code=LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                detail=(
                    f"expected {rules.expected_segment_count} segments, "
                    f"got {segment_count}"
                ),
            )
        try:
            fields = self._map_fields(
                normalized=structural,
                rules=rules,
                label_kind=label_kind,
                schema_version=int(configuration.configuration_schema_version),
                segments=segments,
            )
        except StructuredExtractionError as exc:
            return StructuredExtractionResult(
                raw_payload=raw,
                normalized_payload=structural,
                error_code=exc.code,
                detail=exc.message,
            )

        normalized_fields: dict[str, str | None] = {}
        for key, value in fields.items():
            if value is None:
                normalized_fields[key] = None
                continue
            if key == "quantity":
                normalized_fields[key] = str(value).strip()
            else:
                normalized_fields[key] = self.normalize_field_value(str(value), rules)

        return self._candidate_from_fields(
            raw=raw,
            normalized=structural,
            fields=normalized_fields,
            label_kind=label_kind,
            symbology=symbology,
            recognition_source=recognition_source,
            extra_meta={
                "payload_structure": PayloadStructure.SEGMENTED.value,
                "delimiter_detected": "true" if delimiter_detected else "false",
                "segment_count": str(segment_count),
                "mapped_fields": ",".join(
                    sorted(k for k, v in normalized_fields.items() if v)
                ),
            },
        )

    def _candidate_from_fields(
        self,
        *,
        raw: str,
        normalized: str,
        fields: dict[str, str | None],
        label_kind: LabelKind,
        symbology: str | None,
        recognition_source: RecognitionSource,
        extra_meta: dict[str, str],
    ) -> StructuredExtractionResult:
        meta = {
            "normalized_payload": normalized,
            **{
                k: v
                for k, v in fields.items()
                if k in ("lot", "serial", "expiry_date") and v is not None
            },
            **extra_meta,
        }
        quantity = fields.get("quantity")
        qty_out: int | float | None = None
        if quantity is not None and str(quantity).strip() != "":
            qty_text = str(quantity).strip()
            # Reject decimals here; allow_decimals is enforced in LabelValidationService
            # with profile quantity_rules (keeps extractor free of full qty policy).
            if any(sep in qty_text for sep in (".", ",", " ")):
                return StructuredExtractionResult(
                    raw_payload=raw,
                    normalized_payload=normalized,
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="quantity segment is not an integer",
                )
            try:
                qty_out = int(qty_text)
            except ValueError:
                return StructuredExtractionResult(
                    raw_payload=raw,
                    normalized_payload=normalized,
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="quantity segment is not an integer",
                )

        candidate = CandidateLabel(
            raw_payload=raw,
            recognition_source=recognition_source,
            label_kind_hint=label_kind,
            symbology=symbology,
            label_id=_as_opt_str(fields.get("label_id")),
            sku=_as_opt_str(fields.get("sku")),
            quantity=qty_out,
            position_id=_as_opt_str(fields.get("position_id")),
            pallet=_as_opt_str(fields.get("pallet")),
            side=_as_opt_str(fields.get("side")),
            level=_as_opt_str(fields.get("level")),
            metadata={k: str(v) for k, v in meta.items() if v is not None},
        )
        return StructuredExtractionResult(
            raw_payload=raw,
            normalized_payload=normalized,
            candidate=candidate,
        )

    def _map_gs1_fields(
        self,
        *,
        by_ai: Mapping[str, object],
        rules: DeterministicBarcodeRules,
        label_kind: LabelKind,
    ) -> dict[str, str | None]:
        allowed = (
            ITEM_FIELD_TARGETS
            if label_kind is LabelKind.ITEM
            else POSITION_FIELD_TARGETS
        )
        mappings = [
            m
            for m in rules.field_mappings
            if m.target.strip().lower() in allowed
        ]
        if not mappings:
            raise StructuredExtractionError(
                LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                "GS1 structure requires field_mappings",
            )
        out: dict[str, str | None] = {}
        seen: set[str] = set()
        for mapping in mappings:
            target = mapping.target.strip().lower()
            if target in seen:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    f"duplicate field mapping target {target!r}",
                )
            seen.add(target)
            if mapping.source is not FieldMappingSource.APPLICATION_IDENTIFIER:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "GS1 mappings must use APPLICATION_IDENTIFIER source",
                )
            ai = (mapping.application_identifier or "").strip()
            if not ai:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    f"mapping for {target!r} missing application_identifier",
                )
            field = by_ai.get(ai)
            if field is None:
                out[target] = None
                continue
            out[target] = getattr(field, "normalized_value", None)
        return out

    @staticmethod
    def normalize_structural(raw: str, rules: DeterministicBarcodeRules) -> str:
        """Safe pre-split normalization — preserve delimiter and segment interiors."""
        text = raw
        if rules.normalization.trim_outer_whitespace:
            text = text.strip()
        return text

    @staticmethod
    def normalize_field_value(value: str, rules: DeterministicBarcodeRules) -> str:
        """Per-field identity normalization after structural mapping."""
        text = value
        norm = rules.normalization
        if norm.trim_outer_whitespace:
            text = text.strip()
        if norm.remove_internal_spaces:
            text = "".join(text.split())
        if norm.remove_hyphens:
            text = text.replace("-", "")
        if norm.case_normalization.value == "UPPER":
            text = text.upper()
        elif norm.case_normalization.value == "LOWER":
            text = text.lower()
        return text

    @staticmethod
    def normalize(raw: str, rules: DeterministicBarcodeRules) -> str:
        """Full-payload normalization for SIMPLE identity payloads."""
        text = StructuredPayloadExtractor.normalize_structural(raw, rules)
        return StructuredPayloadExtractor.normalize_field_value(text, rules)

    def _map_fields(
        self,
        *,
        normalized: str,
        rules: DeterministicBarcodeRules,
        label_kind: LabelKind,
        schema_version: int,
        segments: list[str] | None = None,
    ) -> dict[str, str | None]:
        allowed = (
            ITEM_FIELD_TARGETS
            if label_kind is LabelKind.ITEM
            else POSITION_FIELD_TARGETS
        )
        mappings = rules.field_mappings
        applicable = [
            m
            for m in mappings
            if m.target.strip().lower() in allowed
        ]
        if not mappings:
            # Schema v2: never invent label_id=sku=raw. Legacy v1 may adapt.
            if schema_version >= 2:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "configuration_schema_version=2 requires explicit field_mappings",
                )
            if label_kind is LabelKind.ITEM:
                return {"label_id": normalized, "sku": normalized}
            return {"position_id": normalized}
        if not applicable:
            raise StructuredExtractionError(
                LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                f"no field mappings apply to {label_kind.value}",
            )

        seen_targets: set[str] = set()
        for mapping in applicable:
            target = mapping.target.strip().lower()
            if target in seen_targets:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    f"duplicate field mapping target {target!r}",
                )
            seen_targets.add(target)

        resolved_segments = segments
        if rules.payload_structure is PayloadStructure.SEGMENTED and resolved_segments is None:
            delimiter = rules.delimiter or "|"
            if not delimiter or len(delimiter) > _MAX_DELIMITER_LEN:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "invalid segmented delimiter",
                )
            resolved_segments = normalized.split(delimiter)
            if len(resolved_segments) > _MAX_SEGMENTS:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                    f"segment count exceeds {_MAX_SEGMENTS}",
                )
            if (
                rules.expected_segment_count is not None
                and len(resolved_segments) != int(rules.expected_segment_count)
            ):
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                    (
                        f"expected {rules.expected_segment_count} segments, "
                        f"got {len(resolved_segments)}"
                    ),
                )

        out: dict[str, str | None] = {}
        for mapping in applicable:
            target = mapping.target.strip().lower()
            if mapping.source is FieldMappingSource.WHOLE:
                out[target] = normalized
            elif mapping.source is FieldMappingSource.SEGMENT:
                if resolved_segments is None:
                    raise StructuredExtractionError(
                        LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                        "segment mapping requires SEGMENTED structure",
                    )
                idx = mapping.segment_index
                if idx is None or idx < 0 or idx >= len(resolved_segments):
                    raise StructuredExtractionError(
                        LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                        f"segment index {idx} out of range for {len(resolved_segments)} segments",
                    )
                segment_value = resolved_segments[idx]
                if segment_value is None or str(segment_value).strip() == "":
                    raise StructuredExtractionError(
                        LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                        f"mapped segment for {target!r} is empty",
                    )
                out[target] = segment_value
            elif mapping.source is FieldMappingSource.APPLICATION_IDENTIFIER:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "APPLICATION_IDENTIFIER mapping requires GS1 structure",
                )
            else:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    f"unsupported mapping source {mapping.source!r}",
                )
        return out


class StructuredExtractionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _as_opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
