"""Phase 5 — recovery helpers for durable external fallback requests."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.image_processing.external_result_normalizer import (
    EXTERNAL_PROVIDER_STRATEGY,
)
from src.domain.assets.entities import SourceAsset
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.external_image_analysis_request import (
    ExternalImageAnalysisRequest,
    ExternalRequestStatus,
)
from src.domain.jobs.entities import Job


@dataclass(frozen=True)
class ExternalFallbackRecoveryDecision:
    """How recovery should treat an existing durable request row."""

    action: str  # SKIP_PERSISTED | REUSE_NORMALIZED | RECONCILE_PERSISTED | CONTINUE
    request: ExternalImageAnalysisRequest


class ExternalFallbackRecoveryService:
    """Decide recovery without repeating provider cost when a durable response exists."""

    def decide(self, request: ExternalImageAnalysisRequest) -> ExternalFallbackRecoveryDecision:
        if request.status is ExternalRequestStatus.PERSISTED:
            # PERSISTED requires an active position or result — never silent skip.
            if request.position_id or request.active_result_id:
                return ExternalFallbackRecoveryDecision(
                    action="SKIP_PERSISTED", request=request
                )
            return ExternalFallbackRecoveryDecision(
                action="RECONCILE_PERSISTED", request=request
            )
        if (
            request.status
            in (
                ExternalRequestStatus.PROVIDER_SUCCEEDED,
                ExternalRequestStatus.PERSISTENCE_PENDING,
            )
            and request.normalized_result
        ):
            return ExternalFallbackRecoveryDecision(action="REUSE_NORMALIZED", request=request)
        return ExternalFallbackRecoveryDecision(action="CONTINUE", request=request)

    def result_from_stored(
        self,
        request: ExternalImageAnalysisRequest,
        job: Job,
        asset: SourceAsset,
        reason: str,
    ) -> ImageProcessingResult:
        norm = request.normalized_result or {}
        code = norm.get("internal_code")
        qty = norm.get("quantity")
        return ImageProcessingResult(
            job_id=job.id,
            asset_id=asset.id,
            status=ImageResultStatus.RESOLVED_EXTERNAL,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            internal_code=str(code) if code else None,
            quantity=float(qty)
            if isinstance(qty, (int, float)) and not isinstance(qty, bool)
            else None,
            normalized_result=norm,
            additional_fields={
                "fallback_eligible": True,
                "fallback_reason": reason,
                "external_provider": request.provider,
                "external_model": request.model,
                "estimated_cost": request.estimated_cost,
                "reused_normalized_response": True,
            },
            evidence={
                "provider": request.provider,
                "model": request.model,
                "request_image_sha256": request.request_image_sha256,
                "provider_response_sha256": request.provider_response_sha256,
                "normalized_result_sha256": request.normalized_result_sha256,
                "estimated_cost": request.estimated_cost,
            },
            provider_name=request.provider,
            model_name=request.model,
            processing_duration_ms=request.duration_ms,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )


__all__ = [
    "ExternalFallbackRecoveryDecision",
    "ExternalFallbackRecoveryService",
]
