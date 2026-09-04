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

        normalized = self.normalize(raw, rules)
        try:
            fields = self._map_fields(
                normalized=normalized,
                rules=rules,
                label_kind=label_kind,
                schema_version=int(configuration.configuration_schema_version),
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
            extra_meta={},
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
            extra_meta=ai_meta,
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
            try:
                qty_out = int(str(quantity).strip())
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
    def normalize(raw: str, rules: DeterministicBarcodeRules) -> str:
        text = raw
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

    def _map_fields(
        self,
        *,
        normalized: str,
        rules: DeterministicBarcodeRules,
        label_kind: LabelKind,
        schema_version: int,
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

        segments: list[str] | None = None
        if rules.payload_structure is PayloadStructure.SEGMENTED:
            delimiter = rules.delimiter or "|"
            if not delimiter or len(delimiter) > _MAX_DELIMITER_LEN:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "invalid segmented delimiter",
                )
            segments = normalized.split(delimiter)
            if len(segments) > _MAX_SEGMENTS:
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                    f"segment count exceeds {_MAX_SEGMENTS}",
                )
            if (
                rules.expected_segment_count is not None
                and len(segments) != int(rules.expected_segment_count)
            ):
                raise StructuredExtractionError(
                    LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                    (
                        f"expected {rules.expected_segment_count} segments, "
                        f"got {len(segments)}"
                    ),
                )

        out: dict[str, str | None] = {}
        for mapping in applicable:
            target = mapping.target.strip().lower()
            if mapping.source is FieldMappingSource.WHOLE:
                out[target] = normalized
            elif mapping.source is FieldMappingSource.SEGMENT:
                if segments is None:
                    raise StructuredExtractionError(
                        LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                        "segment mapping requires SEGMENTED structure",
                    )
                idx = mapping.segment_index
                if idx is None or idx < 0 or idx >= len(segments):
                    raise StructuredExtractionError(
                        LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                        f"segment index {idx} out of range",
                    )
                out[target] = segments[idx]
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
