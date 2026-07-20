"""Shared field-candidate contract for CODE_SCAN / OCR / EXTERNAL (Phase 6 corrections)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
    ProfileAwareProcessingResultValidator,
    ProfileValidationResult,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    default_extraction_configuration,
)
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)


@dataclass
class FieldCandidateSet:
    """Unified candidates produced by any per-image strategy before profile validation."""

    code_candidates: list[FieldCandidate] = field(default_factory=list)
    quantity_candidates: list[FieldCandidate] = field(default_factory=list)
    additional_fields: dict[str, str] = field(default_factory=dict)
    barcode_format: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def configuration_from_job_snapshot(
    supplier_extraction_profile: dict[str, Any] | None,
) -> ExtractionProfileConfiguration:
    """Parse snapshotted configuration; raise on invalid payload."""
    if not isinstance(supplier_extraction_profile, dict):
        return default_extraction_configuration()
    raw = supplier_extraction_profile.get("configuration")
    try:
        return parse_extraction_configuration(raw if isinstance(raw, dict) else None)
    except ExtractionProfileConfigurationError as exc:
        raise ExtractionProfileConfigurationError(
            "PROFILE_SNAPSHOT_INVALID",
            f"job snapshot supplier_extraction_profile is invalid: {exc.message}",
        ) from exc


def symbology_to_code_source(symbology: str | None) -> str:
    key = (symbology or "").strip().upper()
    if key in {"EAN8", "EAN13", "EAN14", "UPC_A", "UPCA", "UPC"}:
        return "EAN"
    if key in {"QR", "CODE128", "CODE39", "I25", "PDF417", "DATABAR"}:
        return "INTERNAL_CODE"
    return "INTERNAL_CODE"


def apply_profile_validation(
    *,
    job_id: str,
    asset_id: str,
    processing_mode: str,
    resolved_by: str,
    candidates: FieldCandidateSet,
    configuration: ExtractionProfileConfiguration,
    duration_ms: int | None = None,
    provider_name: str | None = None,
    model_name: str | None = None,
    for_external: bool = False,
) -> ImageProcessingResult:
    """Run ProfileAwareProcessingResultValidator and map to ImageProcessingResult."""
    validator = ProfileAwareProcessingResultValidator(configuration)
    outcome: ProfileValidationResult = validator.validate_resolved(
        code_candidates=candidates.code_candidates,
        quantity_candidates=candidates.quantity_candidates,
        barcode_format=candidates.barcode_format,
        additional=candidates.additional_fields,
    )
    evidence = {
        **dict(candidates.evidence),
        "internal_code_source": outcome.internal_code_source,
        "quantity_source": outcome.quantity_source,
        "profile_validation_executed": True,
        "validation_errors": list(outcome.errors),
    }
    if outcome.ok:
        status = (
            ImageResultStatus.RESOLVED_EXTERNAL
            if for_external
            else ImageResultStatus.RESOLVED_INTERNAL
        )
        return ImageProcessingResult(
            job_id=job_id,
            asset_id=asset_id,
            status=status,
            processing_mode=processing_mode,
            resolved_by=resolved_by,
            internal_code=outcome.internal_code,
            quantity=float(outcome.quantity) if outcome.quantity is not None else None,
            additional_fields=dict(outcome.additional_fields),
            normalized_result={
                "internal_code": outcome.internal_code,
                "quantity": outcome.quantity,
                **outcome.additional_fields,
            },
            validation_errors=[],
            warnings=list(candidates.warnings) + list(outcome.warnings),
            evidence=evidence,
            provider_name=provider_name,
            model_name=model_name,
            processing_duration_ms=duration_ms,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )

    missing_both = (
        "MISSING_INTERNAL_CODE" in outcome.errors and "MISSING_QUANTITY" in outcome.errors
    )
    if missing_both and not outcome.internal_code and outcome.quantity is None:
        status = ImageResultStatus.UNRECOGNIZED
        error_code = outcome.errors[0] if outcome.errors else "UNRECOGNIZED"
    elif outcome.errors:
        status = ImageResultStatus.PENDING_MANUAL_REVIEW
        error_code = outcome.errors[0]
    else:
        status = ImageResultStatus.UNRECOGNIZED
        error_code = "UNRECOGNIZED"

    return ImageProcessingResult(
        job_id=job_id,
        asset_id=asset_id,
        status=status,
        processing_mode=processing_mode,
        resolved_by=resolved_by,
        internal_code=outcome.internal_code,
        quantity=float(outcome.quantity) if outcome.quantity is not None else None,
        additional_fields=dict(outcome.additional_fields),
        validation_errors=list(outcome.errors),
        warnings=list(candidates.warnings) + list(outcome.warnings),
        evidence=evidence,
        provider_name=provider_name,
        model_name=model_name,
        processing_duration_ms=duration_ms,
        error_code=error_code,
        error_message="Profile validation failed",
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
    )


__all__ = [
    "FieldCandidateSet",
    "apply_profile_validation",
    "configuration_from_job_snapshot",
    "symbology_to_code_source",
]
