"""Map Vision/EXTERNAL_PROVIDER analysis → CandidateLabel → LabelValidationService.

Recognition (Vision) and validation remain separate. Deterministic rules win over
Vision-inferred fields when a raw payload is present (StructuredPayloadExtractor).
"""

from __future__ import annotations

import hashlib
from typing import Any

from src.application.ports.external_image_analysis_provider import ExternalAnalysisResult
from src.application.services.label_validation import LabelValidationService
from src.application.services.position_recognition import (
    CanonicalPositionValidationCommand,
    CanonicalPositionValidator,
)
from src.domain.image_processing.contracts import (
    RAW_EVIDENCE_HASH_ALGORITHM,
    VISION_POSITION_DETECTOR_NAME,
    VISION_POSITION_DETECTOR_VERSION,
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
    RawEvidenceMetadata,
    VisionPositionEvidence,
)
from src.domain.label_profiles.kinds import LabelKind
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationStatus,
    NormalizedItemLabel,
    NormalizedPositionLabel,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_recognition import PositionRecognitionSource
from src.domain.product_labels.processed import ProcessedProductLabel, ProductLabelOutcomeStatus
from src.observability.metrics.instruments import (
    VisionCandidateMetricComponent,
    VisionCandidateMetricMode,
    VisionCandidateMetricOutcome,
    record_vision_candidate,
)

EXTERNAL_PROVIDER_STRATEGY = "EXTERNAL_PROVIDER"

VISION_POSITION_RAW_EVIDENCE_REQUIRED = "VISION_POSITION_RAW_EVIDENCE_REQUIRED"

_EXPLICIT_RAW_EVIDENCE_FIELDS = (
    "raw_payload",
    "barcode",
    "code_value",
)

_LOGISTIC_SEMANTIC_TYPES = frozenset(
    {
        "LPN",
        "SSCC",
        "LOGISTIC_UNIT",
        "PALLET",
        "BOX",
        "CONTAINER",
    }
)


def _processed_from_normalized_item(
    label: NormalizedItemLabel,
    *,
    detection_index: int,
    semantic_type: str | None,
) -> ProcessedProductLabel:
    semantic = (semantic_type or "").strip().upper() or None
    has_sku = bool((label.sku or "").strip())
    has_label_id = bool((label.label_id or "").strip())
    is_logistic = (semantic in _LOGISTIC_SEMANTIC_TYPES and not has_sku) or (
        has_label_id and not has_sku
    )
    logistic_id = (label.label_id or "").strip() or None if is_logistic else None
    return ProcessedProductLabel(
        label_id=label.label_id,
        internal_code=label.sku,
        quantity=label.quantity,
        format_version="SUPPLIER_LOGISTIC_UNIT" if is_logistic else "SUPPLIER",
        checksum=None,
        validation_status=ProductLabelOutcomeStatus.VALID,
        selected_detection_index=detection_index,
        duplicate_detection_count=1,
        symbology=label.symbology,
        raw_payload=label.raw_payload,
        normalized_payload=label.raw_payload,
        semantic_type=semantic,
        logistic_unit_id=logistic_id,
    )


def _vision_mode(kind: LabelKind) -> VisionCandidateMetricMode:
    return (
        VisionCandidateMetricMode.POSITION
        if kind is LabelKind.POSITION
        else VisionCandidateMetricMode.ITEM
    )


def _validation_outcome(status: LabelValidationStatus) -> VisionCandidateMetricOutcome:
    return {
        LabelValidationStatus.AMBIGUOUS: VisionCandidateMetricOutcome.AMBIGUOUS,
        LabelValidationStatus.INVALID: VisionCandidateMetricOutcome.INVALID,
        LabelValidationStatus.NOT_APPLICABLE: VisionCandidateMetricOutcome.NOT_APPLICABLE,
        LabelValidationStatus.TECHNICAL_ERROR: VisionCandidateMetricOutcome.TECHNICAL_ERROR,
    }.get(status, VisionCandidateMetricOutcome.TECHNICAL_ERROR)


def candidate_from_vision_analysis(
    analysis: ExternalAnalysisResult,
    *,
    label_kind_hint: LabelKind | None = None,
) -> CandidateLabel | None:
    """Build CandidateLabel from provider output without inventing missing fields.

    Precedence for identity:
    1. raw / barcode payload text (deterministic extraction later)
    2. structured provider fields (sku, label_id, position_id, …)
    """
    norm = analysis.normalized_result if isinstance(analysis.normalized_result, dict) else {}
    raw = None
    raw_evidence_source = None
    for key in _EXPLICIT_RAW_EVIDENCE_FIELDS:
        value = norm.get(key)
        if isinstance(value, str) and value.strip():
            raw = value
            raw_evidence_source = key
            break

    sku = None
    for key in ("sku", "internal_code", "gtin", "ean"):
        value = norm.get(key)
        if isinstance(value, str) and value.strip():
            sku = value.strip()
            break
    if sku is None and analysis.internal_code:
        code = str(analysis.internal_code).strip()
        # Preserve legacy SIMPLE WHOLE behavior when internal_code is the only identity.
        if raw is not None and code != raw:
            sku = code

    label_id = None
    for key in ("label_id", "sscc", "lpn", "logistic_unit_id"):
        value = norm.get(key)
        if isinstance(value, str) and value.strip():
            label_id = value.strip()
            break

    position_id = None
    for key in ("position_id", "position", "location"):
        value = norm.get(key)
        if isinstance(value, str) and value.strip():
            position_id = value.strip()
            break

    qty = analysis.quantity
    if qty is None and norm.get("quantity") is not None:
        try:
            qty = int(norm["quantity"])
        except (TypeError, ValueError):
            qty = None

    pallet = norm.get("pallet") if isinstance(norm.get("pallet"), str) else None
    side = norm.get("side") if isinstance(norm.get("side"), str) else None
    level = norm.get("level") if isinstance(norm.get("level"), str) else None

    if raw is None and not any((sku, label_id, position_id, pallet, analysis.internal_code)):
        return None

    hint = label_kind_hint
    if hint is None and position_id:
        hint = LabelKind.POSITION
    elif hint is None and (sku or label_id):
        hint = LabelKind.ITEM

    # Legacy ITEM validation may still use a provider identity as CandidateLabel input.
    # It is explicitly marked non-authoritative and can never produce typed raw evidence.
    if raw is None:
        raw = (
            ""
            if hint is LabelKind.POSITION
            else str(analysis.internal_code or sku or label_id or "")
        )

    return CandidateLabel(
        raw_payload=raw,
        recognition_source=RecognitionSource.VISION,
        label_kind_hint=hint,
        symbology=str(norm["symbology"]).strip()
        if isinstance(norm.get("symbology"), str)
        else None,
        label_id=label_id,
        sku=sku,
        quantity=qty,
        position_id=position_id,
        pallet=pallet.strip() if isinstance(pallet, str) else None,
        side=side.strip() if isinstance(side, str) else None,
        level=level.strip() if isinstance(level, str) else None,
        metadata={
            "provider": analysis.provider_name or "",
            "model": analysis.model_name or "",
            "raw_evidence_source": raw_evidence_source or "",
        },
    )


def normalize_vision_via_label_validation(
    *,
    job_id: str,
    asset_id: str,
    analysis: ExternalAnalysisResult,
    validation_context: LabelValidationContext,
    base_fields: dict[str, Any],
    evidence: dict[str, Any],
    label_validation_service: LabelValidationService | None = None,
    canonical_position_validator: CanonicalPositionValidator | None = None,
) -> ImageProcessingResult:
    """Run Vision candidate through unified LabelValidationService (authority)."""
    service = label_validation_service or LabelValidationService()
    candidate = candidate_from_vision_analysis(analysis)
    if candidate is None:
        record_vision_candidate(
            component=VisionCandidateMetricComponent.CANDIDATE,
            mode=VisionCandidateMetricMode.UNKNOWN,
            outcome=VisionCandidateMetricOutcome.NO_CANDIDATE,
        )
        return ImageProcessingResult(
            job_id=job_id,
            asset_id=asset_id,
            status=ImageResultStatus.UNRECOGNIZED,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            additional_fields={**base_fields, "vision_unified_validation": True},
            normalized_result=analysis.normalized_result,
            evidence={**evidence, "vision_validation": "NO_CANDIDATE"},
            provider_name=analysis.provider_name,
            model_name=analysis.model_name,
            processing_duration_ms=analysis.duration_ms,
            error_code="VISION_NO_LABEL_FOUND",
            error_message="Vision returned no usable candidate fields",
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )

    kind = candidate.label_kind_hint or LabelKind.ITEM
    if (
        kind is LabelKind.POSITION
        and candidate.metadata.get("raw_evidence_source") not in _EXPLICIT_RAW_EVIDENCE_FIELDS
    ):
        record_vision_candidate(
            component=VisionCandidateMetricComponent.VALIDATION,
            mode=VisionCandidateMetricMode.POSITION,
            outcome=VisionCandidateMetricOutcome.RAW_EVIDENCE_REQUIRED,
        )
        return ImageProcessingResult(
            job_id=job_id,
            asset_id=asset_id,
            status=ImageResultStatus.PENDING_MANUAL_REVIEW,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            additional_fields={**base_fields, "vision_unified_validation": True},
            normalized_result=analysis.normalized_result,
            validation_errors=[VISION_POSITION_RAW_EVIDENCE_REQUIRED],
            evidence={
                **evidence,
                "vision_unified_validation": True,
                "vision_validation": VISION_POSITION_RAW_EVIDENCE_REQUIRED,
                "recognition_source": RecognitionSource.VISION.value,
            },
            provider_name=analysis.provider_name,
            model_name=analysis.model_name,
            processing_duration_ms=analysis.duration_ms,
            error_code=VISION_POSITION_RAW_EVIDENCE_REQUIRED,
            error_message="Vision position requires explicitly observed raw evidence",
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )
    result = service.validate(candidate, context=validation_context, label_kind=kind)

    evidence_out = {
        **evidence,
        "vision_unified_validation": True,
        "vision_validation_status": result.status.value,
        "recognition_source": RecognitionSource.VISION.value,
        "resolved_by": EXTERNAL_PROVIDER_STRATEGY,
    }

    if result.status is LabelValidationStatus.AMBIGUOUS:
        record_vision_candidate(
            component=VisionCandidateMetricComponent.VALIDATION,
            mode=_vision_mode(kind),
            outcome=VisionCandidateMetricOutcome.AMBIGUOUS,
        )
        return ImageProcessingResult(
            job_id=job_id,
            asset_id=asset_id,
            status=ImageResultStatus.PENDING_MANUAL_REVIEW,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            additional_fields={**base_fields, "vision_unified_validation": True},
            normalized_result=analysis.normalized_result,
            validation_errors=[result.error_code or "AMBIGUOUS_LABEL_KIND"],
            evidence=evidence_out,
            provider_name=analysis.provider_name,
            model_name=analysis.model_name,
            processing_duration_ms=analysis.duration_ms,
            error_code=result.error_code or "VISION_AMBIGUOUS",
            error_message=(result.detail or "Ambiguous Vision label")[:500],
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )

    if result.status is not LabelValidationStatus.VALID or result.label is None:
        record_vision_candidate(
            component=VisionCandidateMetricComponent.VALIDATION,
            mode=_vision_mode(kind),
            outcome=_validation_outcome(result.status),
        )
        return ImageProcessingResult(
            job_id=job_id,
            asset_id=asset_id,
            status=ImageResultStatus.PENDING_MANUAL_REVIEW
            if result.status is LabelValidationStatus.INVALID
            else ImageResultStatus.UNRECOGNIZED,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            additional_fields={
                **base_fields,
                "vision_unified_validation": True,
                "identity_diagnostics": result.diagnostics,
            },
            normalized_result=analysis.normalized_result,
            validation_errors=[c for c in (result.error_code,) if c],
            evidence={
                **evidence_out,
                "identity_diagnostics": result.diagnostics,
                "rejection_reason": result.error_code,
            },
            provider_name=analysis.provider_name,
            model_name=analysis.model_name,
            processing_duration_ms=analysis.duration_ms,
            error_code=result.error_code or "VISION_VALIDATION_REJECTED",
            error_message=(result.detail or "Vision candidate failed validation")[:500],
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )

    label = result.label
    canonical_position = None
    typed_position_evidence: tuple[VisionPositionEvidence, ...] = ()
    if isinstance(label, NormalizedPositionLabel):
        canonical = (canonical_position_validator or CanonicalPositionValidator()).validate(
            CanonicalPositionValidationCommand(
                candidate=candidate,
                source=PositionRecognitionSource.VISION,
                context=validation_context,
                client_supplier_id=(
                    validation_context.resolved_profiles.position.client_supplier_id
                    if validation_context.resolved_profiles is not None
                    else None
                ),
                structural_result=result,
            )
        )
        evidence_out["canonical_position_validation_status"] = canonical.status.value
        evidence_out["canonical_position_policy_rejection"] = canonical.policy_rejection
        if not canonical.operationally_accepted or canonical.recognition is None:
            record_vision_candidate(
                component=VisionCandidateMetricComponent.CANONICAL_POSITION,
                mode=VisionCandidateMetricMode.POSITION,
                outcome=VisionCandidateMetricOutcome.CANONICAL_REJECTED,
            )
            return ImageProcessingResult(
                job_id=job_id,
                asset_id=asset_id,
                status=ImageResultStatus.PENDING_MANUAL_REVIEW,
                processing_mode=EXTERNAL_PROVIDER_STRATEGY,
                resolved_by=EXTERNAL_PROVIDER_STRATEGY,
                additional_fields={**base_fields, "vision_unified_validation": True},
                normalized_result=analysis.normalized_result,
                validation_errors=[canonical.error_code or canonical.status.value],
                evidence=evidence_out,
                provider_name=analysis.provider_name,
                model_name=analysis.model_name,
                processing_duration_ms=analysis.duration_ms,
                error_code=canonical.error_code or canonical.status.value,
                error_message="Vision position candidate failed authoritative validation",
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )
        canonical_position = canonical.recognition
        raw_code = canonical_position.raw_code
        assert raw_code is not None
        raw_bytes = raw_code.encode("utf-8")
        typed_position_evidence = (
            VisionPositionEvidence(
                recognition=canonical_position,
                client_id=validation_context.client_id or "",
                detector_name=VISION_POSITION_DETECTOR_NAME,
                detector_version=VISION_POSITION_DETECTOR_VERSION,
                raw_evidence=RawEvidenceMetadata(
                    payload_hash=hashlib.sha256(raw_bytes).hexdigest(),
                    utf8_length=len(raw_bytes),
                    hash_algorithm=RAW_EVIDENCE_HASH_ALGORITHM,
                ),
            ),
        )
        evidence_out["position_signature_verification"] = (
            canonical_position.signature.verification.value
        )
        evidence_out["existing_position_label_id"] = canonical.existing_position_label_id

    product_results: list[ProcessedProductLabel] = []
    position_meta: dict[str, Any] | None = None
    primary_code: str | None = None
    primary_qty: float | None = None

    if isinstance(label, NormalizedItemLabel):
        semantic = None
        cfg = validation_context.item_extraction_configuration
        if cfg is not None:
            semantic = getattr(cfg, "semantic_type", None)
        processed = _processed_from_normalized_item(
            label, detection_index=0, semantic_type=semantic
        )
        product_results.append(processed)
        # Identity-only MINIMAL: persist/display via label_id without inventing sku.
        primary_code = (
            (processed.internal_code or "").strip()
            or (processed.label_id or "").strip()
            or (processed.logistic_unit_id or "").strip()
            or None
        )
        primary_qty = float(processed.quantity) if processed.quantity is not None else None
        evidence_out["profile_source"] = label.profile_source.value
    elif isinstance(label, NormalizedPositionLabel):
        if canonical_position is None:
            return ImageProcessingResult(
                job_id=job_id,
                asset_id=asset_id,
                status=ImageResultStatus.FAILED_TECHNICAL,
                processing_mode=EXTERNAL_PROVIDER_STRATEGY,
                resolved_by=EXTERNAL_PROVIDER_STRATEGY,
                additional_fields={**base_fields, "vision_unified_validation": True},
                normalized_result=analysis.normalized_result,
                validation_errors=["CANONICAL_POSITION_RESULT_MISSING"],
                evidence=evidence_out,
                provider_name=analysis.provider_name,
                model_name=analysis.model_name,
                processing_duration_ms=analysis.duration_ms,
                error_code="CANONICAL_POSITION_RESULT_MISSING",
                error_message="Canonical position validation returned no recognition",
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )
        position_meta = {
            "position_id": canonical_position.normalized_code,
            "pallet": canonical_position.pallet,
            "side": canonical_position.side,
            "level": canonical_position.level,
            "position_detection_count": 1,
            "position_ambiguous": False,
            "position_statuses": ["VALID"],
            "client_id": validation_context.client_id,
            "profile_source": label.profile_source.value,
            "recognition_source": RecognitionSource.VISION.value,
            "normalized_positions": [
                {
                    "position_id": canonical_position.normalized_code,
                    "pallet": canonical_position.pallet,
                    "side": canonical_position.side,
                    "level": canonical_position.level,
                    "marker_index": canonical_position.marker_index,
                    "marker_total": canonical_position.marker_total,
                    "client_supplier_id": canonical_position.client_supplier_id,
                    "profile_id": canonical_position.profile_id,
                    "profile_version": canonical_position.profile_version,
                }
            ],
        }
        evidence_out["position_label_detection"] = position_meta
        evidence_out["profile_source"] = label.profile_source.value

    logistic_only = bool(product_results) and all(
        getattr(p, "format_version", None) == "SUPPLIER_LOGISTIC_UNIT" for p in product_results
    )
    cfg = validation_context.item_extraction_configuration
    minimal = bool(cfg is not None and getattr(cfg, "is_minimal", lambda: False)())
    if logistic_only and not minimal:
        status = ImageResultStatus.PENDING_MANUAL_REVIEW
        evidence_out["logistic_unit_review"] = True
        evidence_out["limitation"] = (
            "LOGISTIC_UNIT_NO_PRODUCT_RECORD: SSCC/LPN recognized via Vision; "
            "inventory SKU rows not auto-created"
        )
    elif product_results or position_meta:
        status = ImageResultStatus.RESOLVED_EXTERNAL
        if logistic_only and minimal:
            evidence_out["identity_valid"] = True
            evidence_out["enrichment_complete"] = False
            evidence_out["logistic_unit_identity_only"] = True
    else:
        status = ImageResultStatus.UNRECOGNIZED

    if result.diagnostics:
        evidence_out["identity_diagnostics"] = result.diagnostics

    metric_outcome = (
        VisionCandidateMetricOutcome.RESOLVED
        if status is ImageResultStatus.RESOLVED_EXTERNAL
        else (
            VisionCandidateMetricOutcome.REQUIRES_REVIEW
            if status is ImageResultStatus.PENDING_MANUAL_REVIEW
            else VisionCandidateMetricOutcome.UNRECOGNIZED
        )
    )
    record_vision_candidate(
        component=VisionCandidateMetricComponent.BRIDGE,
        mode=_vision_mode(kind),
        outcome=metric_outcome,
    )
    return ImageProcessingResult(
        job_id=job_id,
        asset_id=asset_id,
        status=status,
        processing_mode=EXTERNAL_PROVIDER_STRATEGY,
        resolved_by=EXTERNAL_PROVIDER_STRATEGY,
        internal_code=primary_code,
        quantity=primary_qty,
        additional_fields={**base_fields, "vision_unified_validation": True},
        normalized_result=analysis.normalized_result
        or {
            "sku": primary_code,
            "quantity": primary_qty,
            "position": position_meta,
        },
        evidence={
            **evidence_out,
            # Pure position photos only — never skip product persistence when both exist.
            **(
                {"result_kind": "POSITION_ONLY"}
                if position_meta is not None and not product_results
                else {}
            ),
        },
        provider_name=analysis.provider_name,
        model_name=analysis.model_name,
        processing_duration_ms=analysis.duration_ms,
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
        product_results=list(product_results),
        vision_position_evidence=typed_position_evidence,
    )


__all__ = [
    "VISION_POSITION_RAW_EVIDENCE_REQUIRED",
    "candidate_from_vision_analysis",
    "normalize_vision_via_label_validation",
]
