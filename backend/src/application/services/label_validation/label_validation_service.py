"""Phase 2 — LabelValidationService: single deterministic validation authority."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping

from src.application.services.label_validation.payload_pattern import (
    PayloadPatternError,
)
from src.application.services.label_validation.payload_pattern import (
    compile_payload_pattern as _compile_payload_pattern_impl,
)
from src.application.services.label_validation.structured_payload_extractor import (
    StructuredPayloadExtractor,
)
from src.application.services.position_label_detection.payload_parser import (
    ParsedPositionLabelPayload,
    PositionLabelPayloadParser,
)
from src.domain.client_supplier.extraction_profile import (
    CharacterSetPolicy,
    ChecksumPolicy,
    ExtractionProfileConfiguration,
    PayloadStructure,
)
from src.domain.label_profiles.entities import ResolvedLabelProfile
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationResult,
    LabelValidationStatus,
    NormalizedItemLabel,
    NormalizedPositionLabel,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_label_detection.entities import PositionLabelDetectionStatus
from src.domain.product_labels.format import (
    ProductLabelValidationStatus,
    parse_product_label_payload,
)

_DEFAULT_POSITION_MAX_PAYLOAD_BYTES = 8192
_NOT_OUR_POSITION_STATUSES = frozenset(
    {
        PositionLabelDetectionStatus.INVALID_JSON,
        PositionLabelDetectionStatus.INVALID_TYPE,
    }
)

logger = logging.getLogger(__name__)

_D1_PREFIX = re.compile(r"^D1\|", re.IGNORECASE)
_DINAMIC_POSITION_HINT = re.compile(r"DINAMIC_POSITION|\"type\"\s*:\s*\"DINAMIC", re.IGNORECASE)

_MAX_PAYLOAD_FOR_REGEX = 512

# Prefer structural / mapping failures over cross-kind PREFIX when both INVALID.
_STRUCTURAL_INVALID_CODES = frozenset(
    {
        LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
        LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
        LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value,
        LabelValidationErrorCode.LABEL_CHARSET_MISMATCH.value,
        LabelValidationErrorCode.LABEL_PATTERN_MISMATCH.value,
        LabelValidationErrorCode.LABEL_GS1_INVALID.value,
        LabelValidationErrorCode.LABEL_GS1_REQUIRED_AI_MISSING.value,
        LabelValidationErrorCode.LABEL_GS1_CHECK_DIGIT_FAILED.value,
        LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value,
        LabelValidationErrorCode.LABEL_GS1_SEPARATOR_INVALID.value,
        LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
        LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
        LabelValidationErrorCode.LABEL_CHECKSUM_FAILED.value,
        LabelValidationErrorCode.DINAMIC_FORMAT_INVALID.value,
        LabelValidationErrorCode.DINAMIC_CHECKSUM_FAILED.value,
        LabelValidationErrorCode.DINAMIC_POSITION_INVALID.value,
    }
)

# Fail-closed Dinamic integrity under SUPPLIER must beat opposite-kind pattern noise.
_DINAMIC_INTEGRITY_CODES = frozenset(
    {
        LabelValidationErrorCode.DINAMIC_FORMAT_INVALID.value,
        LabelValidationErrorCode.DINAMIC_CHECKSUM_FAILED.value,
        LabelValidationErrorCode.DINAMIC_POSITION_INVALID.value,
        LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value,
    }
)

_CROSS_KIND_PATTERN_NOISE = frozenset(
    {
        LabelValidationErrorCode.LABEL_PATTERN_MISMATCH.value,
        LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value,
    }
)

# Re-export for callers that imported context from this module.
__all__ = [
    "LabelProfileConfigurationError",
    "LabelValidationContext",
    "LabelValidationService",
    "compile_payload_pattern",
    "validate_extraction_configuration_for_code_scan",
]


def _kind_validation_summary(result: LabelValidationResult) -> dict[str, object | None]:
    return {
        "status": result.status.value,
        "error_code": result.error_code,
        "detail": result.detail,
        "profile_source": result.profile_source.value if result.profile_source else None,
        "label_kind": result.label_kind.value if result.label_kind else None,
        "profile_id": (result.diagnostics or {}).get("profile_id"),
        "profile_version": (result.diagnostics or {}).get("profile_version"),
    }


def _with_dual_diagnostics(
    result: LabelValidationResult,
    dual: Mapping[str, object],
    *,
    selected_kind: LabelKind | None,
) -> LabelValidationResult:
    merged = {
        **(result.diagnostics or {}),
        **dual,
        "selected_kind": selected_kind.value if selected_kind is not None else None,
    }
    return LabelValidationResult(
        status=result.status,
        label=result.label,
        error_code=result.error_code,
        detail=result.detail,
        profile_source=result.profile_source,
        label_kind=result.label_kind,
        diagnostics=merged,
    )


def _prefer_invalid_when_both_fail(
    item: LabelValidationResult,
    position: LabelValidationResult,
) -> LabelValidationResult:
    """When both kinds INVALID, prefer the structural failure over a PREFIX mismatch.

    Classic misdiagnosis: a POSITION identity payload fails ITEM with
    LABEL_PREFIX_MISMATCH while POSITION fails with LABEL_SEGMENT_COUNT_MISMATCH —
    surfacing only ITEM hides the actionable structural error. Prefer per-kind
    diagnostics; top-level error_code remains for legacy single-code consumers.
    """
    item_code = (item.error_code or "").strip()
    position_code = (position.error_code or "").strip()
    # Dinamic integrity under SUPPLIER is fail-closed and must not be hidden by the
    # opposite kind's pattern/prefix mismatch (e.g. bad D1 vs POSITION regex).
    if item_code in _DINAMIC_INTEGRITY_CODES and position_code in _CROSS_KIND_PATTERN_NOISE:
        return item
    if position_code in _DINAMIC_INTEGRITY_CODES and item_code in _CROSS_KIND_PATTERN_NOISE:
        return position
    item_prefix = item_code == LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value
    position_prefix = position_code == LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value
    item_structural = item_code in _STRUCTURAL_INVALID_CODES
    position_structural = position_code in _STRUCTURAL_INVALID_CODES
    if item_prefix and position_structural and not position_prefix:
        return position
    if position_prefix and item_structural and not item_prefix:
        return item
    if position_structural and not item_structural:
        return position
    if item_structural and not position_structural:
        return item
    # Stable default: prefer POSITION structural diagnostics when codes equal weight,
    # else keep ITEM for legacy single-error consumers (documented dual diagnostics).
    if position_structural and item_structural:
        return position
    return item


class LabelProfileConfigurationError(ValueError):
    """Raised when supplier validation rules are malformed (config-time / load-time)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def compile_payload_pattern(pattern: str):
    """Compile and cache a supplier payload regex; reject unsafe/invalid patterns."""
    try:
        return _compile_payload_pattern_impl(pattern)
    except PayloadPatternError as exc:
        raise LabelProfileConfigurationError(exc.code, exc.message) from exc


def validate_extraction_configuration_for_code_scan(
    configuration: ExtractionProfileConfiguration,
) -> None:
    """Fail early when activating/writing a SUPPLIER profile used by CODE_SCAN."""
    from src.application.services.image_processing.extraction_profile_configuration import (
        ExtractionProfileConfigurationError,
    )
    from src.application.services.label_validation.deterministic_config_validation import (
        validate_deterministic_barcode_rules,
    )

    if configuration.custom_payload_pattern:
        compile_payload_pattern(configuration.custom_payload_pattern)
    code_regex = configuration.validation_rules.code.regex
    if code_regex:
        compile_payload_pattern(code_regex)
    try:
        validate_deterministic_barcode_rules(configuration)
    except ExtractionProfileConfigurationError as exc:
        raise LabelProfileConfigurationError(exc.code, exc.message) from exc


class LabelValidationService:
    """Central deterministic validation entry point."""

    def __init__(
        self,
        *,
        position_parser: PositionLabelPayloadParser | None = None,
        payload_extractor: StructuredPayloadExtractor | None = None,
    ) -> None:
        self._position_parser = position_parser or PositionLabelPayloadParser(
            max_payload_bytes=_DEFAULT_POSITION_MAX_PAYLOAD_BYTES
        )
        self._extractor = payload_extractor or StructuredPayloadExtractor()

    def validate(
        self,
        candidate: CandidateLabel,
        *,
        context: LabelValidationContext,
        label_kind: LabelKind,
    ) -> LabelValidationResult:
        profile = self._profile_for(context, label_kind)
        source = profile.source if profile else LabelProfileSource.DINAMIC

        logger.info(
            "label_validation.start job_id=%s label_kind=%s profile_source=%s "
            "recognition_source=%s symbology=%s",
            context.job_id,
            label_kind.value,
            source.value,
            candidate.recognition_source.value,
            candidate.symbology,
        )

        if source is LabelProfileSource.SUPPLIER:
            dinamic_probe = self._probe_dinamic_integrity(candidate, label_kind)
            if dinamic_probe is not None:
                return dinamic_probe

        if source is LabelProfileSource.DINAMIC:
            result = self._validate_dinamic(candidate, label_kind=label_kind)
        else:
            result = self._validate_supplier(
                candidate,
                label_kind=label_kind,
                context=context,
                profile=profile,
            )

        logger.info(
            "label_validation.result job_id=%s label_kind=%s profile_source=%s "
            "status=%s error_code=%s",
            context.job_id,
            label_kind.value,
            source.value,
            result.status.value,
            result.error_code,
        )
        return result

    def validate_best_effort(
        self,
        candidate: CandidateLabel,
        *,
        context: LabelValidationContext,
    ) -> LabelValidationResult:
        """Evaluate ITEM and POSITION profiles; surface AMBIGUOUS when both VALID.

        Ignores ``label_kind_hint`` so CODE_SCAN cannot get accidental kind precedence.

        When both kinds are INVALID, keep independent diagnostics and prefer the
        top-level ``error_code`` that is *not* a cross-kind PREFIX mismatch when the
        other kind failed for a structural reason (segment/mapping/length/charset).
        """
        item = self.validate(candidate, context=context, label_kind=LabelKind.ITEM)
        position = self.validate(candidate, context=context, label_kind=LabelKind.POSITION)
        dual = {
            "item_validation": _kind_validation_summary(item),
            "position_validation": _kind_validation_summary(position),
        }
        if (
            item.status is LabelValidationStatus.VALID
            and position.status is LabelValidationStatus.VALID
        ):
            return LabelValidationResult(
                status=LabelValidationStatus.AMBIGUOUS,
                error_code=LabelValidationErrorCode.AMBIGUOUS_LABEL_KIND.value,
                detail="payload matches both ITEM and POSITION profiles",
                diagnostics={**dual, "item": item.diagnostics, "position": position.diagnostics},
            )
        if item.status is LabelValidationStatus.VALID:
            return _with_dual_diagnostics(item, dual, selected_kind=LabelKind.ITEM)
        if position.status is LabelValidationStatus.VALID:
            return _with_dual_diagnostics(position, dual, selected_kind=LabelKind.POSITION)
        if (
            item.status is LabelValidationStatus.INVALID
            and position.status is LabelValidationStatus.INVALID
        ):
            chosen = _prefer_invalid_when_both_fail(item, position)
            return _with_dual_diagnostics(
                chosen,
                dual,
                selected_kind=None,
            )
        if item.status is LabelValidationStatus.INVALID:
            return _with_dual_diagnostics(item, dual, selected_kind=None)
        if position.status is LabelValidationStatus.INVALID:
            return _with_dual_diagnostics(position, dual, selected_kind=None)
        fallback = item if item.status is not LabelValidationStatus.NOT_APPLICABLE else position
        return _with_dual_diagnostics(fallback, dual, selected_kind=None)

    def _profile_for(
        self, context: LabelValidationContext, label_kind: LabelKind
    ) -> ResolvedLabelProfile | None:
        if context.resolved_profiles is None:
            return None
        return (
            context.resolved_profiles.item
            if label_kind is LabelKind.ITEM
            else context.resolved_profiles.position
        )

    def _probe_dinamic_integrity(
        self, candidate: CandidateLabel, label_kind: LabelKind
    ) -> LabelValidationResult | None:
        raw = (candidate.raw_payload or "").strip()
        if label_kind is LabelKind.ITEM and _D1_PREFIX.match(raw):
            parsed = parse_product_label_payload(raw)
            if parsed.status is ProductLabelValidationStatus.VALID:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value,
                    detail=(
                        "valid Dinamic D1 payload rejected under SUPPLIER ITEM profile "
                        "(source mismatch; not a format error)"
                    ),
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                )
            if parsed.status is ProductLabelValidationStatus.NOT_OUR_FORMAT:
                return None
            return LabelValidationResult.invalid(
                error_code=(
                    LabelValidationErrorCode.DINAMIC_CHECKSUM_FAILED.value
                    if parsed.status is ProductLabelValidationStatus.CHECKSUM_FAILED
                    else LabelValidationErrorCode.DINAMIC_FORMAT_INVALID.value
                ),
                detail=parsed.detail or parsed.status.value,
                profile_source=LabelProfileSource.DINAMIC,
                label_kind=LabelKind.ITEM,
                diagnostics={"product_label_status": parsed.status.value},
            )
        if label_kind is LabelKind.POSITION and _DINAMIC_POSITION_HINT.search(raw):
            parsed_pos = self._position_parser.parse(raw)
            if parsed_pos.status is PositionLabelDetectionStatus.VALID:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value,
                    detail=(
                        "valid Dinamic POSITION payload rejected under SUPPLIER POSITION "
                        "profile (source mismatch; not a format error)"
                    ),
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.POSITION,
                )
            if parsed_pos.status not in _NOT_OUR_POSITION_STATUSES:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.DINAMIC_POSITION_INVALID.value,
                    detail=parsed_pos.detail or parsed_pos.status.value,
                    profile_source=LabelProfileSource.DINAMIC,
                    label_kind=LabelKind.POSITION,
                )
        return None

    def _validate_dinamic(
        self, candidate: CandidateLabel, *, label_kind: LabelKind
    ) -> LabelValidationResult:
        raw = (candidate.raw_payload or "").strip()
        if label_kind is LabelKind.ITEM:
            parsed = parse_product_label_payload(raw)
            if parsed.status is ProductLabelValidationStatus.NOT_OUR_FORMAT:
                return LabelValidationResult.not_applicable(
                    detail="not Dinamic D1 format",
                    profile_source=LabelProfileSource.DINAMIC,
                    label_kind=LabelKind.ITEM,
                )
            if parsed.status is not ProductLabelValidationStatus.VALID:
                return LabelValidationResult.invalid(
                    error_code=(
                        LabelValidationErrorCode.DINAMIC_CHECKSUM_FAILED.value
                        if parsed.status is ProductLabelValidationStatus.CHECKSUM_FAILED
                        else LabelValidationErrorCode.DINAMIC_FORMAT_INVALID.value
                    ),
                    detail=parsed.detail or parsed.status.value,
                    profile_source=LabelProfileSource.DINAMIC,
                    label_kind=LabelKind.ITEM,
                    diagnostics={"product_label_status": parsed.status.value},
                )
            assert parsed.internal_code is not None
            return LabelValidationResult.valid(
                NormalizedItemLabel(
                    label_id=parsed.label_id,
                    sku=parsed.internal_code,
                    quantity=parsed.quantity,
                    raw_payload=parsed.normalized_payload or raw,
                    profile_source=LabelProfileSource.DINAMIC,
                    format_version=parsed.format_version,
                    symbology=candidate.symbology,
                    checksum_ok=True,
                ),
                profile_source=LabelProfileSource.DINAMIC,
                label_kind=LabelKind.ITEM,
            )

        parsed_pos = self._position_parser.parse(raw)
        return self._dinamic_position_result(parsed_pos, candidate=candidate, raw=raw)

    def _dinamic_position_result(
        self,
        parsed_pos: ParsedPositionLabelPayload,
        *,
        candidate: CandidateLabel,
        raw: str,
    ) -> LabelValidationResult:
        if parsed_pos.status in _NOT_OUR_POSITION_STATUSES:
            return LabelValidationResult.not_applicable(
                detail=parsed_pos.detail or "not Dinamic POSITION format",
                profile_source=LabelProfileSource.DINAMIC,
                label_kind=LabelKind.POSITION,
            )
        if parsed_pos.status is not PositionLabelDetectionStatus.VALID:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.DINAMIC_POSITION_INVALID.value,
                detail=parsed_pos.detail or parsed_pos.status.value,
                profile_source=LabelProfileSource.DINAMIC,
                label_kind=LabelKind.POSITION,
                diagnostics={"position_status": parsed_pos.status.value},
            )
        position_id = (parsed_pos.label_id or "").strip()
        payload = parsed_pos.payload or {}
        return LabelValidationResult.valid(
            NormalizedPositionLabel(
                position_id=position_id,
                pallet=str(payload["pallet"]).strip() if payload.get("pallet") else None,
                side=str(payload["side"]).strip() if payload.get("side") else None,
                level=str(payload["level"]).strip() if payload.get("level") else None,
                raw_payload=raw,
                profile_source=LabelProfileSource.DINAMIC,
                symbology=candidate.symbology,
            ),
            profile_source=LabelProfileSource.DINAMIC,
            label_kind=LabelKind.POSITION,
            diagnostics={
                "position_status": parsed_pos.status.value,
                "position_payload": dict(payload),
            },
        )

    def _validate_supplier(
        self,
        candidate: CandidateLabel,
        *,
        label_kind: LabelKind,
        context: LabelValidationContext,
        profile: ResolvedLabelProfile | None,
    ) -> LabelValidationResult:
        del profile  # used for logging at call site; config comes from snapshot
        config = (
            context.item_extraction_configuration
            if label_kind is LabelKind.ITEM
            else context.position_extraction_configuration
        )
        if config is None:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED.value,
                detail="supplier extraction configuration missing from job snapshot",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )

        if not self._symbology_accepted(
            candidate.symbology,
            config,
            recognition_source=candidate.recognition_source,
        ):
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_SYMBOLOGY_REJECTED.value,
                detail=f"symbology {candidate.symbology!r} not in accepted_barcode_formats",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )

        extracted = self._extractor.extract(
            raw_payload=candidate.raw_payload or "",
            configuration=config,
            label_kind=label_kind,
            symbology=candidate.symbology,
            recognition_source=candidate.recognition_source,
        )
        if not extracted.ok or extracted.candidate is None:
            return LabelValidationResult.invalid(
                error_code=extracted.error_code
                or LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                detail=extracted.detail,
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
                diagnostics={
                    "raw_payload": extracted.raw_payload,
                    "normalized_payload": extracted.normalized_payload,
                },
            )

        structured = extracted.candidate
        rules = config.effective_deterministic()
        normalized = extracted.normalized_payload
        extraction_diags = {
            k: v
            for k, v in (structured.metadata or {}).items()
            if k
            in {
                "payload_structure",
                "delimiter_detected",
                "segment_count",
                "mapped_fields",
                "gs1_application_identifiers",
            }
        }

        if rules.payload_structure is not PayloadStructure.GS1:
            subject, failed_field = self._identity_shape_subject(
                label_kind=label_kind,
                rules=rules,
                normalized_payload=normalized,
                candidate=structured,
            )
            if not subject:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                    detail=f"identity field {failed_field!r} missing after structured extraction",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                    diagnostics={
                        **extraction_diags,
                        "failed_field": failed_field,
                        "validation_error_code": (
                            LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value
                        ),
                    },
                )
            shape_err = self._validate_deterministic_shape(
                normalized=subject,
                rules=rules,
                config=config,
                label_kind=label_kind,
                failed_field=failed_field,
                extra_diagnostics=extraction_diags,
            )
            if shape_err is not None:
                return shape_err

        if label_kind is LabelKind.ITEM:
            result = self._normalize_supplier_item(
                structured, raw=extracted.raw_payload, config=config
            )
        else:
            result = self._normalize_supplier_position(
                structured, raw=extracted.raw_payload, config=config
            )
        if extraction_diags and result.diagnostics is not None:
            merged = {**extraction_diags, **(result.diagnostics or {})}
            return LabelValidationResult(
                status=result.status,
                label=result.label,
                error_code=result.error_code,
                detail=result.detail,
                profile_source=result.profile_source,
                label_kind=result.label_kind,
                diagnostics=merged,
            )
        if extraction_diags and result.diagnostics is None:
            return LabelValidationResult(
                status=result.status,
                label=result.label,
                error_code=result.error_code,
                detail=result.detail,
                profile_source=result.profile_source,
                label_kind=result.label_kind,
                diagnostics=extraction_diags,
            )
        return result

    @staticmethod
    def _identity_shape_subject(
        *,
        label_kind: LabelKind,
        rules,
        normalized_payload: str,
        candidate: CandidateLabel,
    ) -> tuple[str, str]:
        """Return (value, field_name) for prefix/length/charset identity checks.

        SEGMENTED: identity rules apply to the mapped identity field only — never the
        full payload (delimiter + other segments must not affect exact_length).
        SIMPLE: whole normalized payload (equals WHOLE→identity mapping).
        """
        if rules.payload_structure is PayloadStructure.SEGMENTED:
            if label_kind is LabelKind.ITEM:
                if candidate.label_id and str(candidate.label_id).strip():
                    return str(candidate.label_id).strip(), "label_id"
                if candidate.sku and str(candidate.sku).strip():
                    return str(candidate.sku).strip(), "sku"
                return "", "label_id"
            position_id = (candidate.position_id or candidate.label_id or "").strip()
            return position_id, "position_id"
        return normalized_payload, "payload"

    def _validate_deterministic_shape(
        self,
        *,
        normalized: str,
        rules,
        config: ExtractionProfileConfiguration,
        label_kind: LabelKind,
        failed_field: str = "payload",
        extra_diagnostics: dict | None = None,
    ) -> LabelValidationResult | None:
        prefix = (rules.expected_prefix or "").strip()
        diagnostics: dict = {
            **(extra_diagnostics or {}),
            "failed_field": failed_field,
            "found": normalized,
            "prefix": {
                "expected": prefix or None,
                "pass": (not prefix) or normalized.startswith(prefix),
            },
            "length": {
                "found": len(normalized),
                "exact_expected": rules.exact_length,
                "min": rules.min_length,
                "max": rules.max_length,
                "pass": True,
            },
            "charset": {
                "expected": rules.character_set.value,
                "pass": True,
            },
        }
        if prefix and not normalized.startswith(prefix):
            diagnostics["prefix"]["pass"] = False
            diagnostics["validation_error_code"] = (
                LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value
            )
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value,
                detail=(
                    f"PREFIX_MISMATCH on {failed_field}: expected prefix {prefix!r}, "
                    f"found {normalized[: max(len(prefix) + 4, 24)]!r}"
                ),
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
                diagnostics=diagnostics,
            )
        suffix = (rules.expected_suffix or "").strip()
        if suffix and not normalized.endswith(suffix):
            diagnostics["validation_error_code"] = (
                LabelValidationErrorCode.LABEL_SUFFIX_MISMATCH.value
            )
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_SUFFIX_MISMATCH.value,
                detail=f"payload must end with {suffix!r} (field {failed_field})",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
                diagnostics=diagnostics,
            )

        length = len(normalized)
        if rules.exact_length is not None and length != int(rules.exact_length):
            diagnostics["length"]["pass"] = False
            diagnostics["validation_error_code"] = (
                LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value
            )
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value,
                detail=(
                    f"LENGTH_MISMATCH on {failed_field}: expected {rules.exact_length}, "
                    f"found {length}"
                ),
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
                diagnostics=diagnostics,
            )
        if rules.min_length is not None and length < int(rules.min_length):
            diagnostics["length"]["pass"] = False
            diagnostics["validation_error_code"] = (
                LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value
            )
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value,
                detail=(
                    f"LENGTH_MISMATCH on {failed_field}: shorter than min_length "
                    f"{rules.min_length} (found {length})"
                ),
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
                diagnostics=diagnostics,
            )
        if rules.max_length is not None and length > int(rules.max_length):
            diagnostics["length"]["pass"] = False
            diagnostics["validation_error_code"] = (
                LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value
            )
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value,
                detail=(
                    f"LENGTH_MISMATCH on {failed_field}: longer than max_length "
                    f"{rules.max_length} (found {length})"
                ),
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
                diagnostics=diagnostics,
            )

        charset_err = self._validate_charset(normalized, rules.character_set, label_kind)
        if charset_err is not None:
            diagnostics["charset"]["pass"] = False
            diagnostics["validation_error_code"] = (
                LabelValidationErrorCode.LABEL_CHARSET_MISMATCH.value
            )
            return LabelValidationResult.invalid(
                error_code=charset_err.error_code
                or LabelValidationErrorCode.LABEL_CHARSET_MISMATCH.value,
                detail=charset_err.detail or "CHARSET_MISMATCH",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
                diagnostics=diagnostics,
            )

        try:
            pattern_text = None
            if rules.use_advanced_pattern or config.custom_payload_pattern:
                pattern_text = config.custom_payload_pattern or config.validation_rules.code.regex
            if pattern_text:
                compiled = compile_payload_pattern(pattern_text)
                if not compiled.fullmatch(normalized):
                    diagnostics["validation_error_code"] = (
                        LabelValidationErrorCode.LABEL_PATTERN_MISMATCH.value
                    )
                    return LabelValidationResult.invalid(
                        error_code=LabelValidationErrorCode.LABEL_PATTERN_MISMATCH.value,
                        detail=(
                            f"field {failed_field} does not match custom_payload_pattern"
                        ),
                        profile_source=LabelProfileSource.SUPPLIER,
                        label_kind=label_kind,
                        diagnostics=diagnostics,
                    )
            elif config.deterministic is None:
                # Legacy length/charset already applied via effective_deterministic;
                # keep code-rule fallback for hyphen/slash when no v2 charset.
                code_err = self._validate_code_rules(normalized, config, label_kind=label_kind)
                if code_err is not None:
                    return code_err
        except LabelProfileConfigurationError as exc:
            return LabelValidationResult(
                status=LabelValidationStatus.TECHNICAL_ERROR,
                error_code=exc.code,
                detail=exc.message,
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
                diagnostics=diagnostics,
            )

        if rules.checksum_policy is ChecksumPolicy.EAN_GTIN:
            digits = "".join(ch for ch in normalized if ch.isdigit())
            if not self._ean_checksum_ok(digits, config):
                diagnostics["validation_error_code"] = (
                    LabelValidationErrorCode.LABEL_CHECKSUM_FAILED.value
                )
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_CHECKSUM_FAILED.value,
                    detail="EAN/GTIN checksum failed",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                    diagnostics=diagnostics,
                )
        return None

    @staticmethod
    def _ean_checksum_ok(digits: str, config: ExtractionProfileConfiguration) -> bool:
        ean = config.validation_rules.ean
        n = len(digits)
        if n == 8 and ean.allow_ean8:
            body = digits
        elif n == 12 and ean.allow_ean12:
            body = digits
        elif n == 13 and ean.allow_ean13:
            body = digits
        elif n == 14 and ean.allow_ean14:
            body = digits
        else:
            return False
        if not ean.validate_checksum:
            return True
        total = 0
        for i, ch in enumerate(reversed(body[:-1])):
            total += int(ch) * (3 if i % 2 == 0 else 1)
        check = (10 - (total % 10)) % 10
        return check == int(body[-1])

    @staticmethod
    def _validate_charset(
        normalized: str, charset: CharacterSetPolicy, label_kind: LabelKind
    ) -> LabelValidationResult | None:
        if charset is CharacterSetPolicy.ANY:
            return None
        if charset is CharacterSetPolicy.NUMERIC:
            ok = normalized.isdigit()
        elif charset is CharacterSetPolicy.HEX:
            ok = all(ch in "0123456789abcdefABCDEF" for ch in normalized)
        elif charset is CharacterSetPolicy.UPPERCASE_ALPHANUMERIC:
            ok = normalized.isalnum() and normalized.upper() == normalized
        elif charset is CharacterSetPolicy.ALPHANUMERIC:
            ok = normalized.isalnum()
        elif charset is CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN:
            ok = all(ch.isalnum() or ch == "-" for ch in normalized) and bool(normalized)
        else:
            ok = True
        if ok:
            return None
        return LabelValidationResult.invalid(
            error_code=LabelValidationErrorCode.LABEL_CHARSET_MISMATCH.value,
            detail=f"CHARSET_MISMATCH: payload does not match character_set {charset.value}",
            profile_source=LabelProfileSource.SUPPLIER,
            label_kind=label_kind,
        )

    def _normalize_supplier_item(
        self,
        candidate: CandidateLabel,
        *,
        raw: str,
        config: ExtractionProfileConfiguration,
    ) -> LabelValidationResult:
        sku = (candidate.sku or "").strip()
        label_id = (candidate.label_id or "").strip() or None
        quantity = candidate.quantity
        required = {f.strip().lower() for f in config.required_fields}
        # Map legacy internal_code requirement onto sku.
        if ("internal_code" in required or "sku" in required) and not sku:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="sku/internal_code required",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.ITEM,
            )
        if "label_id" in required and not label_id:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="label_id required by supplier profile",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.ITEM,
            )
        if "quantity" in required and quantity is None:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="quantity required by supplier profile",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.ITEM,
            )
        # Do not treat quantity_rules.required as hard fail for MINIMAL identity mode.
        if (
            not config.is_minimal()
            and config.quantity_rules.required
            and "quantity" not in required
            and quantity is None
        ):
            # FULL profiles that still mark quantity_rules.required without listing it:
            # keep prior behavior of requiring quantity via required_fields only.
            pass
        qty_out: int | None = None
        if quantity is not None:
            try:
                qty_out = int(quantity)
            except (TypeError, ValueError):
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="quantity must be an integer",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                    diagnostics={"failed_field": "quantity"},
                )
            qrules = config.quantity_rules
            if not qrules.allow_decimals and isinstance(quantity, float):
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="quantity decimals are not allowed",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                    diagnostics={"failed_field": "quantity"},
                )
            if qty_out < 0 and not qrules.allow_negative:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="quantity must not be negative",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                    diagnostics={"failed_field": "quantity"},
                )
            if qty_out == 0 and int(qrules.minimum) >= 1 and not qrules.allow_negative:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="quantity must be a positive integer",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                    diagnostics={"failed_field": "quantity"},
                )
            if qty_out < int(qrules.minimum):
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail=f"quantity below minimum {qrules.minimum}",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                    diagnostics={"failed_field": "quantity"},
                )
            if qty_out > int(qrules.maximum):
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail=f"quantity above maximum {qrules.maximum}",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                    diagnostics={"failed_field": "quantity"},
                )
        sku_required = "internal_code" in required or "sku" in required
        if not sku:
            semantic = (config.semantic_type or "").strip().upper()
            logistic = semantic in {
                "SSCC",
                "LOGISTIC_UNIT",
                "PALLET",
                "BOX",
                "LPN",
                "CONTAINER",
            }
            # MINIMAL / identity-only: never invent sku=label_id.
            # Logistic FULL profiles: keep label_id without inventing sku.
            # Other FULL profiles: preserve legacy invent when sku is required or
            # when neither field is explicitly required (legacy WHOLE→sku path).
            if config.is_minimal() or (logistic and label_id):
                pass
            elif sku_required or ("label_id" not in required):
                sku = (label_id or "").strip()
        if sku_required and not sku:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="sku/internal_code required",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.ITEM,
            )
        if not sku and not label_id:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="sku or label_id missing after structured extraction",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.ITEM,
            )
        identity_diags = {
            "identity_valid": True,
            "enrichment_complete": bool(sku) and qty_out is not None,
            "recognition_mode": config.recognition_mode.value,
        }
        from src.application.services.label_validation.recognition_completeness import (
            evaluate_recognition_completeness,
        )

        completeness = evaluate_recognition_completeness(
            kind=LabelKind.ITEM,
            configuration=config,
            fields={
                "label_id": label_id,
                "sku": sku,
                "quantity": qty_out,
            },
        )
        identity_diags.update(completeness.to_diagnostics())
        return LabelValidationResult.valid(
            NormalizedItemLabel(
                label_id=label_id,
                sku=sku or None,
                quantity=qty_out,
                raw_payload=raw,
                profile_source=LabelProfileSource.SUPPLIER,
                symbology=candidate.symbology,
                metadata=dict(candidate.metadata),
            ),
            profile_source=LabelProfileSource.SUPPLIER,
            label_kind=LabelKind.ITEM,
            diagnostics=identity_diags,
        )

    def _normalize_supplier_position(
        self,
        candidate: CandidateLabel,
        *,
        raw: str,
        config: ExtractionProfileConfiguration,
    ) -> LabelValidationResult:
        position_id = (candidate.position_id or candidate.label_id or "").strip()
        pallet = (candidate.pallet or "").strip() or None
        side = (candidate.side or "").strip() or None
        level = (candidate.level or "").strip() or None
        if not position_id:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="position_id required",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.POSITION,
            )
        required = {f.strip().lower() for f in config.required_fields}
        if "pallet" in required and not pallet:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="pallet required by supplier POSITION profile",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.POSITION,
            )
        if "side" in required and not side:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="side required by supplier POSITION profile",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.POSITION,
            )
        return LabelValidationResult.valid(
            NormalizedPositionLabel(
                position_id=position_id,
                pallet=pallet,
                side=side,
                level=level,
                raw_payload=raw,
                profile_source=LabelProfileSource.SUPPLIER,
                symbology=candidate.symbology,
                metadata=dict(candidate.metadata),
            ),
            profile_source=LabelProfileSource.SUPPLIER,
            label_kind=LabelKind.POSITION,
        )

    @staticmethod
    def _symbology_accepted(
        symbology: str | None,
        config: ExtractionProfileConfiguration,
        *,
        recognition_source: RecognitionSource | None = None,
    ) -> bool:
        if not config.accepted_barcode_formats:
            return True
        # Vision/OCR/CSV/TXT may lack barcode symbology (text handoff or pre-scanned payload).
        if not symbology and recognition_source in (
            RecognitionSource.VISION,
            RecognitionSource.OCR,
            RecognitionSource.CSV,
            RecognitionSource.TXT,
        ):
            return True
        if not symbology:
            return False
        accepted = {s.strip().upper() for s in config.accepted_barcode_formats}
        sym = symbology.strip().upper().replace("-", "_")
        aliases = {
            "QR_CODE": "QR",
            "QRCODE": "QR",
            "CODE_128": "CODE128",
            "CODE128": "CODE128",
            "EAN_13": "EAN13",
            "EAN_8": "EAN8",
            "UPC_A": "UPC_A",
            "UPCA": "UPC_A",
        }
        normalized = aliases.get(sym, sym)
        return normalized in accepted or sym in accepted

    def _validate_code_rules(
        self,
        raw: str,
        config: ExtractionProfileConfiguration,
        *,
        label_kind: LabelKind,
    ) -> LabelValidationResult | None:
        rules = config.validation_rules.code
        length = len(raw)
        if rules.exact_length is not None and length != rules.exact_length:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                detail=f"code length must be exactly {rules.exact_length}",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )
        if rules.min_length is not None and length < rules.min_length:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                detail=f"code shorter than min_length {rules.min_length}",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )
        if rules.max_length is not None and length > rules.max_length:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                detail=f"code longer than max_length {rules.max_length}",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )
        for ch in raw:
            if ch.isalpha() and not rules.allow_letters:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="letters not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
            if ch.isdigit() and not rules.allow_digits:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="digits not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
            if ch == "-" and not rules.allow_hyphen:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="hyphen not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
            if ch == "/" and not rules.allow_slash:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="slash not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
            if ch.isspace() and not rules.allow_spaces:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="spaces not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
        return None
