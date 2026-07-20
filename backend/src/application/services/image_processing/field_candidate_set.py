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


# Profile ``accepted_barcode_formats`` uses compact names (QR, CODE128, EAN13, …).
# pyzbar / ZXing evidence symbology uses QR_CODE / CODE_128 / EAN_13. Normalize both
# sides before comparison so profile-aware CODE_SCAN does not reject valid symbols.
_BARCODE_FORMAT_CANONICAL: dict[str, str] = {
    "QR": "QR",
    "QRCODE": "QR",
    "QR_CODE": "QR",
    "MICROQR": "QR",
    "RMQR": "QR",
    "CODE128": "CODE128",
    "CODE_128": "CODE128",
    "CODE39": "CODE39",
    "CODE_39": "CODE39",
    "EAN13": "EAN13",
    "EAN_13": "EAN13",
    "EAN8": "EAN8",
    "EAN_8": "EAN8",
    "EAN14": "EAN14",
    "EAN_14": "EAN14",
    "UPC_A": "UPC_A",
    "UPCA": "UPC_A",
    "UPC": "UPC_A",
    "UPC_E": "UPC_E",
    "UPCE": "UPC_E",
    "DATAMATRIX": "DATAMATRIX",
    "DATA_MATRIX": "DATAMATRIX",
    "I25": "I25",
    "PDF417": "PDF417",
    "DATABAR": "DATABAR",
}


def normalize_barcode_format_for_profile(fmt: str | None) -> str | None:
    """Map decoder/evidence symbology names onto profile accepted-format vocabulary."""
    if fmt is None:
        return None
    key = str(fmt).strip().upper().replace("-", "_")
    if not key:
        return None
    return _BARCODE_FORMAT_CANONICAL.get(key, key)


def symbology_to_code_source(symbology: str | None) -> str:
    key = normalize_barcode_format_for_profile(symbology) or ""
    if key in {"EAN8", "EAN13", "EAN14", "UPC_A", "UPC_E"}:
        return "EAN"
    if key in {"QR", "CODE128", "CODE39", "I25", "PDF417", "DATABAR", "DATAMATRIX"}:
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
    from src.domain.client_supplier.extraction_profile import UnanchoredCodeCandidatePolicy

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
    policy = configuration.validation_rules.code.unanchored_candidate_policy
    unanchored_selected = any(
        (not c.labeled)
        and c.source_key.upper() == "INTERNAL_CODE"
        and (c.extraction_method or "") == "NUMERIC_PATTERN"
        and outcome.internal_code
        and c.value.replace(" ", "") == (outcome.internal_code or "").replace(" ", "")
        for c in candidates.code_candidates
    )
    # First-correction policy: unanchored strong codes never auto-resolve.
    force_manual_unanchored = (
        unanchored_selected
        and policy is UnanchoredCodeCandidatePolicy.ALLOW_FOR_MANUAL_REVIEW
        and outcome.internal_code
    )

    if outcome.ok and not force_manual_unanchored:
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

    errors = list(outcome.errors)
    warnings = list(candidates.warnings) + list(outcome.warnings)
    if force_manual_unanchored:
        warnings.append("UNANCHORED_CODE_REQUIRES_REVIEW")
        if "MISSING_QUANTITY" not in errors and outcome.quantity is None:
            errors.append("MISSING_QUANTITY")

    # Prefer MissingQuantityResolutionPolicy when code is present and qty missing.
    if outcome.internal_code and outcome.quantity is None:
        from src.application.services.image_processing.missing_quantity_resolution_policy import (
            MissingQuantityResolutionPolicy,
        )

        mq = MissingQuantityResolutionPolicy().resolve(
            rules=configuration.quantity_rules,
            has_valid_internal_code=True,
            quantity_found=False,
        )
        if mq is not None:
            evidence["missing_quantity_policy"] = mq.reason
            evidence["fallback_eligible"] = mq.allow_external_fallback
            return ImageProcessingResult(
                job_id=job_id,
                asset_id=asset_id,
                status=mq.status,
                processing_mode=processing_mode,
                resolved_by=resolved_by,
                internal_code=outcome.internal_code,
                quantity=None,
                additional_fields=dict(outcome.additional_fields),
                validation_errors=list(dict.fromkeys(errors + [mq.error_code])),
                warnings=warnings,
                evidence=evidence,
                provider_name=provider_name,
                model_name=model_name,
                processing_duration_ms=duration_ms,
                error_code=mq.error_code,
                error_message="Profile validation failed",
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )

    if force_manual_unanchored and outcome.internal_code:
        return ImageProcessingResult(
            job_id=job_id,
            asset_id=asset_id,
            status=ImageResultStatus.PENDING_MANUAL_REVIEW,
            processing_mode=processing_mode,
            resolved_by=resolved_by,
            internal_code=outcome.internal_code,
            quantity=float(outcome.quantity) if outcome.quantity is not None else None,
            additional_fields=dict(outcome.additional_fields),
            validation_errors=list(dict.fromkeys(errors or ["UNANCHORED_CODE_REQUIRES_REVIEW"])),
            warnings=warnings,
            evidence=evidence,
            provider_name=provider_name,
            model_name=model_name,
            processing_duration_ms=duration_ms,
            error_code="UNANCHORED_CODE_REQUIRES_REVIEW",
            error_message="Unanchored code requires manual review",
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )

    missing_both = "MISSING_INTERNAL_CODE" in errors and "MISSING_QUANTITY" in errors
    if missing_both and not outcome.internal_code and outcome.quantity is None:
        status = ImageResultStatus.UNRECOGNIZED
        error_code = errors[0] if errors else "UNRECOGNIZED"
    elif errors:
        status = ImageResultStatus.PENDING_MANUAL_REVIEW
        error_code = errors[0]
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
        validation_errors=list(errors),
        warnings=warnings,
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
    "normalize_barcode_format_for_profile",
    "symbology_to_code_source",
]
