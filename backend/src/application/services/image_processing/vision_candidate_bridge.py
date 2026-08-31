"""Map Vision/EXTERNAL_PROVIDER analysis → CandidateLabel → LabelValidationService.

Recognition (Vision) and validation remain separate. Deterministic rules win over
Vision-inferred fields when a raw payload is present (StructuredPayloadExtractor).
"""

from __future__ import annotations

import logging
from typing import Any

from src.application.ports.external_image_analysis_provider import ExternalAnalysisResult
from src.application.services.label_validation import LabelValidationService
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
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
from src.domain.product_labels.processed import ProcessedProductLabel, ProductLabelOutcomeStatus

logger = logging.getLogger(__name__)

EXTERNAL_PROVIDER_STRATEGY = "EXTERNAL_PROVIDER"

_VISION_RESOLVED_TOTAL = "vision_resolved_total"
_VISION_REJECTED_TOTAL = "vision_validation_rejected_total"

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


def _metrics_increment(name: str, *, labels: dict[str, str] | None = None) -> None:
    logger.info(
        "metric.name=%s metric.value=1 labels=%s",
        name,
        labels or {},
    )


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
    for key in (
        "raw_payload",
        "raw",
        "barcode",
        "code_value",
        "payload",
        "scanned_value",
    ):
        value = norm.get(key)
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            break
    if raw is None and analysis.internal_code:
        # Prefer treating provider code as raw when no explicit payload — extractor may apply.
        raw = str(analysis.internal_code).strip()

    sku = None
    for key in ("sku", "internal_code", "gtin", "ean"):
        value = norm.get(key)
        if isinstance(value, str) and value.strip():
            sku = value.strip()
            break
    if sku is None and analysis.internal_code:
        code = str(analysis.internal_code).strip()
        # When raw equals provider code, leave sku unset so SIMPLE WHOLE→label_id|sku mapping decides.
        if raw is None or code != raw:
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

    if not raw and not any((sku, label_id, position_id, pallet)):
        return None

    # Synthetic raw for structured-only Vision output (validator requires raw or identity).
    if not raw:
        raw = sku or label_id or position_id or ""

    hint = label_kind_hint
    if hint is None and position_id:
        hint = LabelKind.POSITION
    elif hint is None and (sku or label_id):
        hint = LabelKind.ITEM

    return CandidateLabel(
        raw_payload=raw,
        recognition_source=RecognitionSource.VISION,
        label_kind_hint=hint,
        symbology=str(norm["symbology"]).strip() if isinstance(norm.get("symbology"), str) else None,
        label_id=label_id,
        sku=sku,
        quantity=qty,
        position_id=position_id,
        pallet=pallet.strip() if isinstance(pallet, str) else None,
        side=side.strip() if isinstance(side, str) else None,
        level=level.strip() if isinstance(level, str) else None,
        metadata={"provider": analysis.provider_name or "", "model": analysis.model_name or ""},
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
) -> ImageProcessingResult:
    """Run Vision candidate through unified LabelValidationService (authority)."""
    service = label_validation_service or LabelValidationService()
    candidate = candidate_from_vision_analysis(analysis)
    if candidate is None:
        _metrics_increment(_VISION_REJECTED_TOTAL, labels={"reason": "NO_CANDIDATE"})
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
    result = service.validate(candidate, context=validation_context, label_kind=kind)

    evidence_out = {
        **evidence,
        "vision_unified_validation": True,
        "vision_validation_status": result.status.value,
        "recognition_source": RecognitionSource.VISION.value,
        "resolved_by": EXTERNAL_PROVIDER_STRATEGY,
    }

    if result.status is LabelValidationStatus.AMBIGUOUS:
        _metrics_increment(_VISION_REJECTED_TOTAL, labels={"reason": "AMBIGUOUS"})
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
        _metrics_increment(_VISION_REJECTED_TOTAL, labels={"reason": result.status.value})
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
        position_meta = {
            "position_id": label.position_id,
            "pallet": label.pallet,
            "side": label.side,
            "level": label.level,
            "raw_payload": label.raw_payload,
            "profile_source": label.profile_source.value,
            "recognition_source": RecognitionSource.VISION.value,
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

    _metrics_increment(
        _VISION_RESOLVED_TOTAL,
        labels={"label_kind": kind.value, "status": status.value},
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
        evidence=evidence_out,
        provider_name=analysis.provider_name,
        model_name=analysis.model_name,
        processing_duration_ms=analysis.duration_ms,
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
        product_results=list(product_results),
    )


__all__ = [
    "candidate_from_vision_analysis",
    "normalize_vision_via_label_validation",
]
