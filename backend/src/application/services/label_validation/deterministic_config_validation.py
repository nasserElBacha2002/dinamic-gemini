"""Validate deterministic barcode configuration before save/activate."""

from __future__ import annotations

from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
)
from src.application.services.label_validation.payload_pattern import (
    PayloadPatternError,
    compile_payload_pattern,
)
from src.domain.client_supplier.extraction_profile import (
    ITEM_FIELD_TARGETS,
    POSITION_FIELD_TARGETS,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    FieldMappingSource,
    PayloadStructure,
)
from src.domain.label_profiles.kinds import LabelKind
from src.domain.label_validation import LabelValidationErrorCode

_SUPPORTED_GS1_AIS = frozenset({"00", "01", "02", "10", "17", "21", "37"})
_MAX_EXAMPLES = 32
_MAX_EXAMPLE_PAYLOAD = 512


def validate_deterministic_barcode_rules(
    configuration: ExtractionProfileConfiguration,
    *,
    label_kind: LabelKind | None = None,
) -> None:
    """Fail closed on contradictory / unsupported deterministic config."""
    rules = configuration.effective_deterministic()
    _validate_length_invariants(rules)
    if rules.payload_structure is PayloadStructure.GS1:
        _validate_gs1_rules(rules)
    if rules.payload_structure is PayloadStructure.SEGMENTED:
        delimiter = rules.delimiter or "|"
        if not delimiter or len(delimiter) > 8:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                "SEGMENTED structure requires a delimiter of 1..8 characters",
            )
        if rules.expected_segment_count is not None and int(rules.expected_segment_count) < 1:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value,
                "expected_segment_count must be >= 1",
            )
    _validate_mappings(rules, label_kind=label_kind)
    _validate_examples_shape(configuration)
    if rules.use_advanced_pattern or configuration.custom_payload_pattern:
        pattern = configuration.custom_payload_pattern or configuration.validation_rules.code.regex
        if not pattern:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
                "use_advanced_pattern requires custom_payload_pattern",
            )
        try:
            compile_payload_pattern(pattern)
        except PayloadPatternError as exc:
            raise ExtractionProfileConfigurationError(exc.code, exc.message) from exc


def _validate_gs1_rules(rules: DeterministicBarcodeRules) -> None:
    required = tuple(str(a).strip() for a in rules.required_application_identifiers if str(a).strip())
    optional = tuple(str(a).strip() for a in rules.optional_application_identifiers if str(a).strip())
    if not required and not rules.field_mappings:
        raise ExtractionProfileConfigurationError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            "GS1 structure requires required_application_identifiers or field_mappings",
        )
    for ai in (*required, *optional):
        if ai not in _SUPPORTED_GS1_AIS:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
                f"unsupported GS1 Application Identifier {ai!r} in PR2 MVP",
            )
    if rules.delimiter:
        raise ExtractionProfileConfigurationError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            "GS1 structure must not set segmented delimiter",
        )


def _validate_examples_shape(configuration: ExtractionProfileConfiguration) -> None:
    for kind, examples in (
        ("valid_examples", configuration.valid_examples),
        ("invalid_examples", configuration.invalid_examples),
    ):
        if len(examples) > _MAX_EXAMPLES:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
                f"{kind} exceeds {_MAX_EXAMPLES} entries",
            )
        for idx, example in enumerate(examples):
            payload = example.raw_payload or ""
            if not str(payload).strip():
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
                    f"{kind}[{idx}].raw_payload is required",
                )
            if len(payload) > _MAX_EXAMPLE_PAYLOAD:
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
                    f"{kind}[{idx}].raw_payload exceeds length limit",
                )


def _validate_length_invariants(rules: DeterministicBarcodeRules) -> None:
    exact = rules.exact_length
    min_l = rules.min_length
    max_l = rules.max_length
    if exact is not None and exact < 1:
        raise ExtractionProfileConfigurationError(
            LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value,
            "exact_length must be >= 1",
        )
    if min_l is not None and max_l is not None and int(min_l) > int(max_l):
        raise ExtractionProfileConfigurationError(
            LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value,
            "min_length cannot exceed max_length",
        )
    if exact is not None and min_l is not None and int(exact) < int(min_l):
        raise ExtractionProfileConfigurationError(
            LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value,
            "exact_length contradicts min_length",
        )
    if exact is not None and max_l is not None and int(exact) > int(max_l):
        raise ExtractionProfileConfigurationError(
            LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value,
            "exact_length contradicts max_length",
        )


def _validate_mappings(
    rules: DeterministicBarcodeRules, *, label_kind: LabelKind | None
) -> None:
    if not rules.field_mappings:
        return
    allowed = ITEM_FIELD_TARGETS | POSITION_FIELD_TARGETS
    if label_kind is LabelKind.ITEM:
        allowed = ITEM_FIELD_TARGETS
    elif label_kind is LabelKind.POSITION:
        allowed = POSITION_FIELD_TARGETS
    seen: set[str] = set()
    for mapping in rules.field_mappings:
        target = mapping.target.strip().lower()
        if target not in allowed:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                f"unsupported field mapping target {target!r}",
            )
        if target in seen:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                f"duplicate field mapping target {target!r}",
            )
        seen.add(target)
        if mapping.source is FieldMappingSource.SEGMENT:
            if rules.payload_structure is not PayloadStructure.SEGMENTED:
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "segment mapping requires SEGMENTED structure",
                )
            if mapping.segment_index is None or mapping.segment_index < 0:
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "segment_index must be a non-negative integer",
                )
        elif mapping.source is FieldMappingSource.WHOLE:
            if mapping.segment_index is not None:
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "WHOLE mapping must not set segment_index",
                )
            if mapping.application_identifier:
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "WHOLE mapping must not set application_identifier",
                )
        elif mapping.source is FieldMappingSource.APPLICATION_IDENTIFIER:
            if rules.payload_structure is not PayloadStructure.GS1:
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "APPLICATION_IDENTIFIER mapping requires GS1 structure",
                )
            ai = (mapping.application_identifier or "").strip()
            if not ai:
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "application_identifier is required for AI mappings",
                )
            if ai not in _SUPPORTED_GS1_AIS:
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    f"unsupported GS1 Application Identifier {ai!r} in mapping",
                )
            if mapping.segment_index is not None:
                raise ExtractionProfileConfigurationError(
                    LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                    "AI mapping must not set segment_index",
                )
        else:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_FIELD_MAPPING_INVALID.value,
                f"unsupported mapping source {mapping.source!r}",
            )
