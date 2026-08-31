"""Activation-time validation of profile valid/invalid examples."""

from __future__ import annotations

from typing import Any

from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
)
from src.application.services.label_validation.label_validation_service import (
    LabelValidationService,
)
from src.domain.client_supplier.extraction_profile import ExtractionProfileConfiguration
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext


def validate_profile_examples_for_activation(
    configuration: ExtractionProfileConfiguration,
    *,
    label_kind: LabelKind,
    validation_service: LabelValidationService | None = None,
) -> None:
    """Ensure valid examples validate and invalid examples do not.

    Draft saves may omit examples; activation requires consistency when examples exist.
    """
    if not configuration.valid_examples and not configuration.invalid_examples:
        return

    svc = validation_service or LabelValidationService()
    context = _supplier_context(configuration, label_kind=label_kind)

    for idx, example in enumerate(configuration.valid_examples):
        result = svc.validate(
            CandidateLabel(
                raw_payload=example.raw_payload,
                recognition_source=RecognitionSource.CODE_SCAN,
                symbology=example.symbology,
                label_kind_hint=label_kind,
            ),
            context=context,
            label_kind=label_kind,
        )
        if result.status is not LabelValidationStatus.VALID:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_PROFILE_EXAMPLE_MISMATCH.value,
                _format_mismatch(
                    kind="valid_examples",
                    index=idx,
                    expected="VALID",
                    actual=result.status.value,
                    error_code=result.error_code,
                ),
            )

    for idx, example in enumerate(configuration.invalid_examples):
        result = svc.validate(
            CandidateLabel(
                raw_payload=example.raw_payload,
                recognition_source=RecognitionSource.CODE_SCAN,
                symbology=example.symbology,
                label_kind_hint=label_kind,
            ),
            context=context,
            label_kind=label_kind,
        )
        if result.status is LabelValidationStatus.VALID:
            raise ExtractionProfileConfigurationError(
                LabelValidationErrorCode.LABEL_PROFILE_EXAMPLE_MISMATCH.value,
                _format_mismatch(
                    kind="invalid_examples",
                    index=idx,
                    expected="NOT_VALID",
                    actual=result.status.value,
                    error_code=None,
                ),
            )


def example_diagnostics_dict(
    *,
    kind: str,
    index: int,
    expected: str,
    actual: str,
    error_code: str | None,
) -> dict[str, Any]:
    return {
        "example_kind": kind,
        "example_index": index,
        "expected_validity": expected,
        "actual_status": actual,
        "error_code": error_code,
    }


def _format_mismatch(
    *,
    kind: str,
    index: int,
    expected: str,
    actual: str,
    error_code: str | None,
) -> str:
    parts = [
        f"{kind}[{index}] expected {expected}, got {actual}",
    ]
    if error_code:
        parts.append(f"error_code={error_code}")
    return "; ".join(parts)


def _supplier_context(
    configuration: ExtractionProfileConfiguration, *, label_kind: LabelKind
) -> LabelValidationContext:
    item_cfg = configuration if label_kind is LabelKind.ITEM else None
    pos_cfg = configuration if label_kind is LabelKind.POSITION else None
    return LabelValidationContext(
        resolved_profiles=ResolvedLabelProfiles(
            item=ResolvedLabelProfile(
                label_kind=LabelKind.ITEM,
                source=LabelProfileSource.SUPPLIER,
                client_supplier_id="activation-check",
                resolution_source="ACTIVATION",
            ),
            position=ResolvedLabelProfile(
                label_kind=LabelKind.POSITION,
                source=LabelProfileSource.SUPPLIER,
                client_supplier_id="activation-check",
                resolution_source="ACTIVATION",
            ),
        ),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=pos_cfg,
    )
