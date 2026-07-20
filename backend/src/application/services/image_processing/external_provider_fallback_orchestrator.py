"""Phase 5 — selective per-asset external fallback after an internal strategy fails."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisContext,
    ExternalAnalysisStatus,
    ExternalImageAnalysisProvider,
    ExternalImageInput,
)
from src.application.ports.image_processing_repositories import ProcessingAttemptRepository
from src.application.services.image_processing.external_circuit_breaker import (
    ExternalCircuitBreaker,
)
from src.application.services.image_processing.external_concurrency_limiter import (
    ExternalConcurrencyLimiter,
)
from src.application.services.image_processing.external_fallback_prompt import (
    EXTERNAL_FALLBACK_PROMPT_KEY,
    EXTERNAL_FALLBACK_PROMPT_VERSION,
)
from src.application.services.image_processing.external_result_normalizer import (
    EXTERNAL_PROVIDER_STRATEGY,
    ExternalResultNormalizer,
)
from src.application.services.image_processing.fallback_eligibility_policy import (
    FallbackEligibilityPolicy,
)
from src.domain.assets.entities import SourceAsset
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.processing_attempt import ProcessingAttemptStatus
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

ContentReader = Callable[[SourceAsset], bytes]


@dataclass
class FallbackProgressCounters:
    fallback_requested: int = 0
    fallback_skipped: int = 0
    fallback_in_progress: int = 0
    resolved_external: int = 0
    external_unrecognized: int = 0
    external_failed: int = 0
    pending_manual_review: int = 0
    estimated_external_cost: float = 0.0
    resolved_internal: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "fallback_requested": self.fallback_requested,
            "fallback_skipped": self.fallback_skipped,
            "fallback_in_progress": self.fallback_in_progress,
            "resolved_external": self.resolved_external,
            "external_unrecognized": self.external_unrecognized,
            "external_failed": self.external_failed,
            "pending_manual_review": self.pending_manual_review,
            "estimated_external_cost": round(self.estimated_external_cost, 6)
            if self.estimated_external_cost
            else None,
            "resolved_internal": self.resolved_internal,
        }


@dataclass(frozen=True)
class ExternalFallbackSnapshot:
    enabled: bool
    provider: str
    model: str | None
    prompt_key: str
    prompt_version: str
    timeout_seconds: float
    max_attempts: int
    max_concurrency: int
    max_image_dimension: int
    quantity_max: int
    circuit_breaker_threshold: int
    circuit_breaker_cooldown_seconds: float
    multi_provider_enabled: bool = False
    snapshot_version: int = 1
    client_rules: dict[str, Any] | None = None
    recoverable_technical_codes: tuple[str, ...] = ()

    @classmethod
    def from_identification_execution(cls, block: dict[str, Any] | None) -> ExternalFallbackSnapshot | None:
        if not isinstance(block, dict):
            return None
        raw = block.get("external_fallback")
        if not isinstance(raw, dict):
            return None
        return cls(
            enabled=bool(raw.get("fallback_enabled") or raw.get("enabled")),
            provider=str(raw.get("fallback_provider") or raw.get("provider") or "").strip().lower(),
            model=(str(raw["fallback_model"]).strip() if raw.get("fallback_model") else None)
            or (str(raw["model"]).strip() if raw.get("model") else None),
            prompt_key=str(raw.get("prompt_key") or EXTERNAL_FALLBACK_PROMPT_KEY),
            prompt_version=str(raw.get("prompt_version") or EXTERNAL_FALLBACK_PROMPT_VERSION),
            timeout_seconds=float(raw.get("timeout_seconds") or 60),
            max_attempts=max(1, int(raw.get("max_attempts") or 1)),
            max_concurrency=max(1, int(raw.get("concurrency") or raw.get("max_concurrency") or 1)),
            max_image_dimension=int(raw.get("max_image_dimension") or 2048),
            quantity_max=int(raw.get("quantity_max") or 99_999_999),
            circuit_breaker_threshold=int(raw.get("circuit_breaker_threshold") or 5),
            circuit_breaker_cooldown_seconds=float(
                raw.get("circuit_breaker_cooldown_seconds") or 60
            ),
            multi_provider_enabled=bool(raw.get("multi_provider_enabled", False)),
            snapshot_version=int(raw.get("snapshot_version") or block.get("snapshot_version") or 1),
            client_rules=raw.get("client_rules")
            if isinstance(raw.get("client_rules"), dict)
            else block.get("client_rules")
            if isinstance(block.get("client_rules"), dict)
            else None,
            recoverable_technical_codes=tuple(
                str(c) for c in (raw.get("recoverable_technical_codes") or [])
            ),
        )


@dataclass
class ExternalProviderFallbackOrchestrator:
    """Runs at most one primary external provider for a single unresolved asset."""

    provider: ExternalImageAnalysisProvider
    content_reader: ContentReader
    attempt_repo: ProcessingAttemptRepository
    clock: Clock
    eligibility: FallbackEligibilityPolicy
    normalizer: ExternalResultNormalizer = field(default_factory=ExternalResultNormalizer)
    circuit_breaker: ExternalCircuitBreaker | None = None
    concurrency_limiter: ExternalConcurrencyLimiter | None = None
    counters: FallbackProgressCounters | None = None
    is_cancelled: Callable[[], bool] | None = None

    def process_if_eligible(
        self,
        *,
        job: Job,
        asset: SourceAsset,
        internal_result: ImageProcessingResult,
        worker_token: str,
        snapshot: ExternalFallbackSnapshot,
    ) -> ImageProcessingResult | None:
        """Return an external ImageProcessingResult, or None when fallback is skipped."""
        # Immutable job snapshot is the feature gate (not live env on retry).
        if not snapshot.enabled:
            if self.counters is not None:
                self.counters.fallback_skipped += 1
            logger.info(
                "fallback.skipped job_id=%s asset_id=%s reason=SNAPSHOT_DISABLED",
                job.id,
                asset.id,
            )
            return None

        decision = self.eligibility.evaluate(internal_result)
        logger.info(
            "fallback.eligibility_evaluated job_id=%s asset_id=%s eligible=%s reason=%s "
            "internal_status=%s error_code=%s",
            job.id,
            asset.id,
            decision.eligible,
            decision.reason,
            internal_result.status.value,
            internal_result.error_code,
        )
        if not decision.eligible:
            if self.counters is not None:
                self.counters.fallback_skipped += 1
            logger.info(
                "fallback.skipped job_id=%s asset_id=%s reason=%s",
                job.id,
                asset.id,
                decision.reason,
            )
            return None

        if self._already_succeeded_externally(job.id, asset.id):
            if self.counters is not None:
                self.counters.fallback_skipped += 1
            logger.info(
                "fallback.skipped job_id=%s asset_id=%s reason=PRIOR_EXTERNAL_SUCCESS",
                job.id,
                asset.id,
            )
            return None

        provider_name = snapshot.provider or self.provider.provider_name
        model_name = snapshot.model or self.provider.model_name
        breaker = self.circuit_breaker
        if breaker is not None and breaker.is_open(provider_name, model_name):
            if self.counters is not None:
                self.counters.external_failed += 1
            logger.warning(
                "fallback.circuit_open job_id=%s asset_id=%s provider=%s model=%s",
                job.id,
                asset.id,
                provider_name,
                model_name,
            )
            return ImageProcessingResult(
                job_id=job.id,
                asset_id=asset.id,
                status=ImageResultStatus.FAILED_TECHNICAL,
                processing_mode=EXTERNAL_PROVIDER_STRATEGY,
                resolved_by=EXTERNAL_PROVIDER_STRATEGY,
                additional_fields={
                    "fallback_executed": False,
                    "fallback_eligible": True,
                    "fallback_reason": decision.reason,
                    "external_provider": provider_name,
                    "external_model": model_name,
                },
                provider_name=provider_name,
                model_name=model_name,
                error_code="EXTERNAL_PROVIDER_CIRCUIT_OPEN",
                error_message="External provider circuit breaker is open",
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )

        if self._cancelled():
            return None

        if self.counters is not None:
            self.counters.fallback_requested += 1
            self.counters.fallback_in_progress += 1

        logger.info(
            "fallback.requested job_id=%s asset_id=%s provider=%s model=%s reason=%s",
            job.id,
            asset.id,
            provider_name,
            model_name,
            decision.reason,
        )

        attempt = self.attempt_repo.create_next_attempt(
            job_id=job.id,
            asset_id=asset.id,
            strategy=EXTERNAL_PROVIDER_STRATEGY,
            status=ProcessingAttemptStatus.STARTED,
            now=self.clock.now(),
            provider=provider_name,
            model=model_name,
            execution_scope=ExecutionScope.SINGLE_ASSET.value,
            configuration_snapshot_version=job.configuration_snapshot_version,
            worker_token=worker_token,
            logical_asset_attempt=False,
        )
        logger.info(
            "fallback.attempt_started job_id=%s asset_id=%s attempt_id=%s provider=%s model=%s",
            job.id,
            asset.id,
            attempt.id,
            provider_name,
            model_name,
        )

        result: ImageProcessingResult
        try:
            if self._cancelled():
                result = self._cancelled_result(job, asset, provider_name, model_name, decision.reason)
            else:
                result = self._execute_provider(
                    job=job,
                    asset=asset,
                    snapshot=snapshot,
                    provider_name=provider_name,
                    model_name=model_name,
                    eligibility_reason=decision.reason,
                )
        except Exception as exc:
            logger.exception(
                "fallback.provider_failed job_id=%s asset_id=%s", job.id, asset.id
            )
            if breaker is not None:
                breaker.record_failure(provider_name, model_name)
            result = ImageProcessingResult(
                job_id=job.id,
                asset_id=asset.id,
                status=ImageResultStatus.FAILED_TECHNICAL,
                processing_mode=EXTERNAL_PROVIDER_STRATEGY,
                resolved_by=EXTERNAL_PROVIDER_STRATEGY,
                additional_fields={
                    "fallback_executed": True,
                    "fallback_eligible": True,
                    "fallback_reason": decision.reason,
                },
                provider_name=provider_name,
                model_name=model_name,
                error_code="EXTERNAL_PROVIDER_EXCEPTION",
                error_message=str(exc)[:500],
                execution_scope=ExecutionScope.SINGLE_ASSET,
                logical_asset_attempt=False,
            )

        self._close_attempt(attempt, result)
        self._update_counters(result)
        if self.counters is not None:
            self.counters.fallback_in_progress = max(0, self.counters.fallback_in_progress - 1)
        return result

    def _execute_provider(
        self,
        *,
        job: Job,
        asset: SourceAsset,
        snapshot: ExternalFallbackSnapshot,
        provider_name: str,
        model_name: str,
        eligibility_reason: str,
    ) -> ImageProcessingResult:
        limiter = self.concurrency_limiter or ExternalConcurrencyLimiter(1)
        with limiter.acquire(timeout=snapshot.timeout_seconds) as acquired:
            if not acquired:
                return ImageProcessingResult(
                    job_id=job.id,
                    asset_id=asset.id,
                    status=ImageResultStatus.FAILED_TECHNICAL,
                    processing_mode=EXTERNAL_PROVIDER_STRATEGY,
                    resolved_by=EXTERNAL_PROVIDER_STRATEGY,
                    additional_fields={
                        "fallback_executed": False,
                        "fallback_reason": eligibility_reason,
                    },
                    provider_name=provider_name,
                    model_name=model_name,
                    error_code="EXTERNAL_CONCURRENCY_TIMEOUT",
                    error_message="Could not acquire external concurrency slot",
                    execution_scope=ExecutionScope.SINGLE_ASSET,
                    logical_asset_attempt=False,
                )

            if self._cancelled():
                return self._cancelled_result(
                    job, asset, provider_name, model_name, eligibility_reason
                )

            content = self.content_reader(asset)
            analysis = self.provider.analyze_image(
                ExternalImageInput(
                    content=content,
                    mime_type=getattr(asset, "content_type", None) or "image/jpeg",
                    asset_id=asset.id,
                    original_filename=getattr(asset, "original_filename", None),
                ),
                ExternalAnalysisContext(
                    job_id=job.id,
                    asset_id=asset.id,
                    client_id=None,
                    prompt_key=snapshot.prompt_key,
                    prompt_version=snapshot.prompt_version,
                    timeout_seconds=snapshot.timeout_seconds,
                    max_image_dimension=snapshot.max_image_dimension,
                    quantity_max=snapshot.quantity_max,
                    configuration_snapshot_version=job.configuration_snapshot_version,
                    extra={"client_rules": snapshot.client_rules or {}},
                ),
            )

        breaker = self.circuit_breaker
        if analysis.status in (
            ExternalAnalysisStatus.TIMEOUT,
            ExternalAnalysisStatus.RATE_LIMITED,
            ExternalAnalysisStatus.FAILED_TECHNICAL,
        ):
            if breaker is not None:
                breaker.record_failure(provider_name, model_name)
            logger.warning(
                "fallback.provider_failed job_id=%s asset_id=%s status=%s error_code=%s",
                job.id,
                asset.id,
                analysis.status.value,
                analysis.error_code,
            )
        else:
            if breaker is not None:
                breaker.record_success(provider_name, model_name)
            logger.info(
                "fallback.provider_completed job_id=%s asset_id=%s status=%s duration_ms=%s "
                "estimated_cost=%s",
                job.id,
                asset.id,
                analysis.status.value,
                analysis.duration_ms,
                analysis.estimated_cost,
            )

        result = self.normalizer.normalize(
            job_id=job.id,
            asset_id=asset.id,
            analysis=analysis,
            quantity_max=snapshot.quantity_max,
        )
        result.additional_fields["fallback_eligible"] = True
        result.additional_fields["fallback_reason"] = eligibility_reason
        result.additional_fields["external_attempt_strategy"] = EXTERNAL_PROVIDER_STRATEGY
        if result.status is ImageResultStatus.PENDING_MANUAL_REVIEW:
            logger.info(
                "fallback.validation_failed job_id=%s asset_id=%s errors=%s",
                job.id,
                asset.id,
                result.validation_errors,
            )
        return result

    def _already_succeeded_externally(self, job_id: str, asset_id: str) -> bool:
        for attempt in self.attempt_repo.list_by_job_and_asset(job_id, asset_id):
            if (
                attempt.strategy == EXTERNAL_PROVIDER_STRATEGY
                and attempt.status is ProcessingAttemptStatus.SUCCEEDED
            ):
                return True
        return False

    def _close_attempt(self, attempt, result: ImageProcessingResult) -> None:
        now = self.clock.now()
        attempt.status = {
            ImageResultStatus.RESOLVED_EXTERNAL: ProcessingAttemptStatus.SUCCEEDED,
            ImageResultStatus.UNRECOGNIZED: ProcessingAttemptStatus.UNRECOGNIZED,
            ImageResultStatus.FAILED_TECHNICAL: ProcessingAttemptStatus.FAILED_TECHNICAL,
            ImageResultStatus.PENDING_MANUAL_REVIEW: ProcessingAttemptStatus.INVALID,
        }.get(result.status, ProcessingAttemptStatus.FAILED_TECHNICAL)
        attempt.finished_at = now
        if attempt.started_at is not None:
            attempt.duration_ms = int((now - attempt.started_at).total_seconds() * 1000)
        elif result.processing_duration_ms is not None:
            attempt.duration_ms = result.processing_duration_ms
        attempt.error_code = result.error_code
        attempt.error_message = result.error_message
        attempt.normalized_result = result.normalized_result
        attempt.validation_result = {
            "errors": list(result.validation_errors),
            "warnings": list(result.warnings),
        }
        attempt.provider = result.provider_name or attempt.provider
        attempt.model = result.model_name or attempt.model
        attempt.execution_scope = ExecutionScope.SINGLE_ASSET.value
        attempt.extra = {
            **dict(attempt.extra or {}),
            "estimated_cost": (result.additional_fields or {}).get("estimated_cost"),
            "prompt_key": EXTERNAL_FALLBACK_PROMPT_KEY,
            "prompt_version": (result.additional_fields or {}).get("prompt_version"),
            "raw_reference": (result.additional_fields or {}).get("raw_reference"),
            "fallback_reason": (result.additional_fields or {}).get("fallback_reason"),
        }
        if result.evidence and result.evidence.get("response_hash"):
            attempt.raw_result_reference = str(result.evidence["response_hash"])
        self.attempt_repo.save(attempt)

    def _update_counters(self, result: ImageProcessingResult) -> None:
        if self.counters is None:
            return
        cost = (result.additional_fields or {}).get("estimated_cost")
        if isinstance(cost, (int, float)):
            self.counters.estimated_external_cost += float(cost)
        if result.status is ImageResultStatus.RESOLVED_EXTERNAL:
            self.counters.resolved_external += 1
        elif result.status is ImageResultStatus.UNRECOGNIZED:
            self.counters.external_unrecognized += 1
        elif result.status is ImageResultStatus.FAILED_TECHNICAL:
            self.counters.external_failed += 1
        elif result.status is ImageResultStatus.PENDING_MANUAL_REVIEW:
            self.counters.pending_manual_review += 1

    def _cancelled(self) -> bool:
        return bool(self.is_cancelled and self.is_cancelled())

    def _cancelled_result(
        self,
        job: Job,
        asset: SourceAsset,
        provider_name: str,
        model_name: str,
        reason: str,
    ) -> ImageProcessingResult:
        return ImageProcessingResult(
            job_id=job.id,
            asset_id=asset.id,
            status=ImageResultStatus.FAILED_TECHNICAL,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            additional_fields={
                "fallback_executed": False,
                "fallback_reason": reason,
                "cancelled": True,
            },
            provider_name=provider_name,
            model_name=model_name,
            error_code="JOB_CANCELLED",
            error_message="Job cancelled before external provider call",
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )


def build_external_fallback_snapshot_dict(
    *,
    enabled: bool,
    provider: str,
    model: str | None,
    timeout_seconds: float,
    max_attempts: int,
    max_concurrency: int,
    max_image_dimension: int,
    quantity_max: int,
    circuit_breaker_threshold: int,
    circuit_breaker_cooldown_seconds: float,
    multi_provider_enabled: bool = False,
    snapshot_version: int,
    client_rules: dict | None = None,
    recoverable_technical_codes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "fallback_enabled": bool(enabled),
        "fallback_provider": (provider or "").strip().lower(),
        "fallback_model": model,
        "fallback_order": [(provider or "").strip().lower()] if provider else [],
        "prompt_key": EXTERNAL_FALLBACK_PROMPT_KEY,
        "prompt_version": EXTERNAL_FALLBACK_PROMPT_VERSION,
        "timeout_seconds": float(timeout_seconds),
        "max_attempts": int(max_attempts),
        "concurrency": int(max_concurrency),
        "concurrency_profile": {"max_external": int(max_concurrency)},
        "max_image_dimension": int(max_image_dimension),
        "quantity_max": int(quantity_max),
        "circuit_breaker_threshold": int(circuit_breaker_threshold),
        "circuit_breaker_cooldown_seconds": float(circuit_breaker_cooldown_seconds),
        "circuit_breaker_profile": {
            "threshold": int(circuit_breaker_threshold),
            "cooldown_seconds": float(circuit_breaker_cooldown_seconds),
        },
        "multi_provider_enabled": bool(multi_provider_enabled),
        "validation_profile": "shared_image_processing",
        "cost_profile": "llm_cost_snapshot",
        "snapshot_version": int(snapshot_version),
        "client_rules": client_rules,
        "recoverable_technical_codes": list(recoverable_technical_codes or []),
    }


__all__ = [
    "ExternalFallbackSnapshot",
    "ExternalProviderFallbackOrchestrator",
    "FallbackProgressCounters",
    "build_external_fallback_snapshot_dict",
]
