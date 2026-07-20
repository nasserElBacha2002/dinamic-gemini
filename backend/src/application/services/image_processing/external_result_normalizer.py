"""Phase 5 — map ExternalAnalysisResult → ImageProcessingResult (no persistence)."""

from __future__ import annotations

from typing import Any

from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
)
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)

EXTERNAL_PROVIDER_STRATEGY = "EXTERNAL_PROVIDER"


def _apply_client_code_priority(
    *,
    code: str | None,
    normalized: dict[str, Any] | None,
    client_rules: dict[str, Any] | None,
) -> str | None:
    """Deterministic code selection from snapshot client_rules (not prompt-only).

    When prefer_ean_as_internal_code is set, prefer EAN-like fields from the
    normalized payload over a non-EAN provider code when both exist.
    """
    if not client_rules:
        return code
    prefer_ean = bool(client_rules.get("prefer_ean_as_internal_code"))
    if not prefer_ean:
        return code
    candidates: list[str] = []
    if isinstance(normalized, dict):
        for key in ("ean", "ean_label", "bare_ean", "EAN", "codigo_ean"):
            raw = normalized.get(key)
            if isinstance(raw, str) and raw.strip():
                candidates.append(raw.strip())
        fields = normalized.get("fields")
        if isinstance(fields, dict):
            for key in ("ean", "EAN", "ean_label"):
                raw = fields.get(key)
                if isinstance(raw, str) and raw.strip():
                    candidates.append(raw.strip())
    for cand in candidates:
        digits = "".join(ch for ch in cand if ch.isdigit())
        if len(digits) in (8, 12, 13, 14):
            return digits
    return code


class ExternalResultNormalizer:
    """Normalize provider adapter output into the shared image-processing contract."""

    def normalize(
        self,
        *,
        job_id: str,
        asset_id: str,
        analysis: ExternalAnalysisResult,
        quantity_max: int = 99_999_999,
        client_rules: dict[str, Any] | None = None,
        client_id: str | None = None,
    ) -> ImageProcessingResult:
        base_fields = {
            "fallback_executed": True,
            "external_provider": analysis.provider_name,
            "external_model": analysis.model_name,
            "prompt_version": analysis.prompt_version,
            "estimated_cost": analysis.estimated_cost,
            "usage": analysis.usage,
            "raw_reference": analysis.raw_reference,
            "client_id": client_id,
            "client_rule_key": (client_rules or {}).get("client_rule_key")
            if client_rules
            else None,
        }
        evidence = {
            "provider": analysis.provider_name,
            "model": analysis.model_name,
            "prompt_version": analysis.prompt_version,
            "request_image_sha256": (analysis.additional_fields or {}).get(
                "request_image_sha256"
            ),
            "provider_response_sha256": analysis.raw_reference
            or (analysis.additional_fields or {}).get("provider_response_sha256"),
            "normalized_result": analysis.normalized_result,
            "confidence": analysis.confidence,
            "usage": analysis.usage,
            "estimated_cost": analysis.estimated_cost,
            "duration_ms": analysis.duration_ms,
            "warnings": list(analysis.warnings),
            "validation_errors": list(analysis.validation_errors),
            "client_id": client_id,
        }

        if analysis.status is ExternalAnalysisStatus.TIMEOUT:
            return self._technical(
                job_id,
                asset_id,
                analysis,
                base_fields,
                evidence,
                "EXTERNAL_PROVIDER_TIMEOUT",
            )
        if analysis.status is ExternalAnalysisStatus.RATE_LIMITED:
            return self._technical(
                job_id,
                asset_id,
                analysis,
                base_fields,
                evidence,
                "EXTERNAL_PROVIDER_RATE_LIMITED",
            )
        if analysis.status is ExternalAnalysisStatus.FAILED_TECHNICAL:
            return self._technical(
                job_id,
                asset_id,
                analysis,
                base_fields,
                evidence,
                analysis.error_code or "EXTERNAL_PROVIDER_FAILED",
            )

        if analysis.status is ExternalAnalysisStatus.AMBIGUOUS:
            return ImageProcessingResult(
                job_id=job_id,
                asset_id=asset_id,
                status=ImageResultStatus.PENDING_MANUAL_REVIEW,
                processing_mode=EXTERNAL_PROVIDER_STRATEGY,
                resolved_by=EXTERNAL_PROVIDER_STRATEGY,
                internal_code=analysis.internal_code,
                quantity=analysis.quantity,
                additional_fields=base_fields,
                normalized_result=analysis.normalized_result,
                validation_errors=list(analysis.validation_errors) + ["AMBIGUOUS_EXTERNAL"],
                warnings=list(analysis.warnings),
                evidence=evidence,
                provider_name=analysis.provider_name,
                model_name=analysis.model_name,
                processing_duration_ms=analysis.duration_ms,
                error_code="AMBIGUOUS_EXTERNAL",
                error_message=(analysis.error_message or "Multiple labels detected")[:500],
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )

        if analysis.status in (
            ExternalAnalysisStatus.NO_RESULT,
            ExternalAnalysisStatus.INVALID,
        ):
            return ImageProcessingResult(
                job_id=job_id,
                asset_id=asset_id,
                status=ImageResultStatus.UNRECOGNIZED,
                processing_mode=EXTERNAL_PROVIDER_STRATEGY,
                resolved_by=EXTERNAL_PROVIDER_STRATEGY,
                additional_fields=base_fields,
                normalized_result=analysis.normalized_result,
                validation_errors=list(analysis.validation_errors),
                warnings=list(analysis.warnings),
                evidence=evidence,
                provider_name=analysis.provider_name,
                model_name=analysis.model_name,
                processing_duration_ms=analysis.duration_ms,
                error_code=analysis.error_code or "EXTERNAL_NO_RESULT",
                error_message=(analysis.error_message or "Provider returned no usable label")[
                    :500
                ],
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )

        # VALID — still apply business validation (never trust provider alone).
        code = (analysis.internal_code or "").strip() or None
        code = _apply_client_code_priority(
            code=code,
            normalized=analysis.normalized_result
            if isinstance(analysis.normalized_result, dict)
            else None,
            client_rules=client_rules,
        )
        qty = analysis.quantity
        errors: list[str] = list(analysis.validation_errors)
        required = list(
            (client_rules or {}).get("required_fields") or ["internal_code", "quantity"]
        )
        if "internal_code" in required and not code:
            errors.append("MISSING_CODE")
        if "quantity" in required and qty is None:
            errors.append("MISSING_QUANTITY")
        elif qty is not None and (
            isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0
        ):
            errors.append("INVALID_QUANTITY")
            qty = None
        elif isinstance(qty, int) and qty > int(quantity_max):
            errors.append("QUANTITY_ABOVE_MAX")

        if errors:
            return ImageProcessingResult(
                job_id=job_id,
                asset_id=asset_id,
                status=ImageResultStatus.PENDING_MANUAL_REVIEW,
                processing_mode=EXTERNAL_PROVIDER_STRATEGY,
                resolved_by=EXTERNAL_PROVIDER_STRATEGY,
                internal_code=code,
                quantity=qty,
                additional_fields=base_fields,
                normalized_result=analysis.normalized_result,
                validation_errors=errors,
                warnings=list(analysis.warnings),
                evidence=evidence,
                provider_name=analysis.provider_name,
                model_name=analysis.model_name,
                processing_duration_ms=analysis.duration_ms,
                error_code=errors[0],
                error_message="External result failed business validation",
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )

        return ImageProcessingResult(
            job_id=job_id,
            asset_id=asset_id,
            status=ImageResultStatus.RESOLVED_EXTERNAL,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            internal_code=code,
            quantity=float(qty) if qty is not None else None,
            additional_fields=base_fields,
            normalized_result=analysis.normalized_result
            or {"internal_code": code, "quantity": qty},
            validation_errors=[],
            warnings=list(analysis.warnings),
            evidence=evidence,
            provider_name=analysis.provider_name,
            model_name=analysis.model_name,
            processing_duration_ms=analysis.duration_ms,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )

    def _technical(
        self,
        job_id: str,
        asset_id: str,
        analysis: ExternalAnalysisResult,
        base_fields: dict,
        evidence: dict,
        error_code: str,
    ) -> ImageProcessingResult:
        return ImageProcessingResult(
            job_id=job_id,
            asset_id=asset_id,
            status=ImageResultStatus.FAILED_TECHNICAL,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            additional_fields=base_fields,
            evidence=evidence,
            provider_name=analysis.provider_name,
            model_name=analysis.model_name,
            processing_duration_ms=analysis.duration_ms,
            error_code=error_code,
            error_message=(analysis.error_message or error_code)[:500],
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )


__all__ = ["EXTERNAL_PROVIDER_STRATEGY", "ExternalResultNormalizer"]
