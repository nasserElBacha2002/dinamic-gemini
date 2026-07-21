"""Phase 5 — selective per-asset external fallback (corrections: lifecycle + recovery)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.application.ports.clock import Clock
from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisContext,
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
    ExternalImageAnalysisProvider,
    ExternalImageInput,
)
from src.application.ports.external_image_analysis_request_repository import (
    ExternalImageAnalysisRequestRepository,
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
from src.application.services.image_processing.external_fallback_recovery import (
    ExternalFallbackRecoveryDecision,
    ExternalFallbackRecoveryService,
)
from src.application.services.image_processing.external_result_normalizer import (
    EXTERNAL_PROVIDER_STRATEGY,
    ExternalResultNormalizer,
)
from src.application.services.image_processing.fallback_eligibility_policy import (
    DEFAULT_RECOVERABLE_TECHNICAL_CODES,
    FallbackEligibilityPolicy,
)
from src.application.services.image_processing.processing_event_publisher import (
    ProcessingEventPublisher,
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
    build_external_idempotency_key,
)
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

ContentReader = Callable[[SourceAsset], bytes]

_RETRYABLE_ANALYSIS = frozenset(
    {
        ExternalAnalysisStatus.TIMEOUT,
        ExternalAnalysisStatus.RATE_LIMITED,
        ExternalAnalysisStatus.FAILED_TECHNICAL,
    }
)


class ExternalProviderFactory(Protocol):
    def resolve(self, *, provider: str, model: str | None) -> ExternalImageAnalysisProvider: ...


@dataclass
class FallbackProgressCounters:
    """Process-local accumulator; reconcile against DB via aggregate_fallback_progress."""

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
    retry_backoff_seconds: float = 0.5
    supplier_extraction_profile: dict[str, Any] | None = None
    profile_aware_validation_enabled: bool = False
    ambiguous_internal_code_fallback_enabled: bool = False

    @classmethod
    def from_identification_execution(
        cls, block: dict[str, Any] | None
    ) -> ExternalFallbackSnapshot | None:
        if not isinstance(block, dict):
            return None
        raw = block.get("external_fallback")
        if not isinstance(raw, dict):
            return None
        flags = block.get("feature_flag_state")
        profile_aware = False
        if isinstance(flags, dict):
            profile_aware = bool(flags.get("profile_aware_validation_enabled"))
        profile_snap = block.get("supplier_extraction_profile")
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
            retry_backoff_seconds=float(raw.get("retry_backoff_seconds") or 0.5),
            supplier_extraction_profile=profile_snap if isinstance(profile_snap, dict) else None,
            profile_aware_validation_enabled=profile_aware,
            ambiguous_internal_code_fallback_enabled=bool(
                raw.get("ambiguous_internal_code_fallback_enabled", False)
            ),
        )


@dataclass
class ExternalFallbackOutcome:
    """Result of one fallback evaluation. Attempt is SUCCEEDED only after persist finalize."""

    skipped: bool = False
    cancelled: bool = False
    result: ImageProcessingResult | None = None
    attempt: ProcessingAttempt | None = None
    request: ExternalImageAnalysisRequest | None = None
    provider_call_status: str | None = None
    persistence_status: str | None = None


@dataclass
class ExternalProviderFallbackOrchestrator:
    """Coordinates eligibility → claim → provider → normalize; persist is finalized by caller."""

    content_reader: ContentReader
    attempt_repo: ProcessingAttemptRepository
    request_repo: ExternalImageAnalysisRequestRepository
    clock: Clock
    provider_factory: ExternalProviderFactory
    normalizer: ExternalResultNormalizer = field(default_factory=ExternalResultNormalizer)
    circuit_breaker: ExternalCircuitBreaker | None = None
    concurrency_limiter: ExternalConcurrencyLimiter | None = None
    counters: FallbackProgressCounters | None = None
    is_cancelled: Callable[[], bool] | None = None
    #: Legacy single-provider injection (tests); preferred path is provider_factory + snapshot.
    provider: ExternalImageAnalysisProvider | None = None
    recovery: ExternalFallbackRecoveryService = field(
        default_factory=ExternalFallbackRecoveryService
    )
    event_publisher: ProcessingEventPublisher | None = None

    def _publish_fallback_event(
        self,
        *,
        job_id: str,
        asset_id: str,
        event_type: str,
        message: str | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
        severity: str = "INFO",
    ) -> None:
        if self.event_publisher is None:
            return
        try:
            self.event_publisher.publish(
                job_id=job_id,
                asset_id=asset_id,
                event_type=event_type,
                strategy="EXTERNAL_PROVIDER",
                severity=severity,
                message=message,
                error_code=error_code,
                metadata=metadata,
            )
        except Exception:
            # Best-effort observability only — never affect fallback processing.
            logger.warning(
                "fallback.event_publish_failed job_id=%s asset_id=%s event=%s",
                job_id,
                asset_id,
                event_type,
                exc_info=True,
            )

    def process_if_eligible(
        self,
        *,
        job: Job,
        asset: SourceAsset,
        internal_result: ImageProcessingResult,
        worker_token: str,
        snapshot: ExternalFallbackSnapshot,
        client_id: str | None = None,
    ) -> ExternalFallbackOutcome:
        eligibility = FallbackEligibilityPolicy(
            enabled=bool(snapshot.enabled),
            recoverable_technical_codes=frozenset(snapshot.recoverable_technical_codes)
            if snapshot.recoverable_technical_codes
            else DEFAULT_RECOVERABLE_TECHNICAL_CODES,
            ambiguous_internal_code_fallback_enabled=bool(
                snapshot.ambiguous_internal_code_fallback_enabled
            ),
        )
        decision = eligibility.evaluate(internal_result)
        eval_metadata = {
            "asset_id": asset.id,
            "internal_status": getattr(
                internal_result.status, "value", str(internal_result.status)
            ),
            "internal_error_code": internal_result.error_code,
            "validation_errors": list(internal_result.validation_errors or [])[:20],
            "has_internal_code": bool(
                internal_result.internal_code and str(internal_result.internal_code).strip()
            ),
            "has_quantity": internal_result.quantity is not None,
            "fallback_enabled": bool(snapshot.enabled),
            "eligible": decision.eligible,
            "reason": decision.reason,
            "next_strategy": decision.next_strategy,
            "provider": snapshot.provider,
            "model": snapshot.model,
        }
        logger.info(
            "fallback.evaluated job_id=%s asset_id=%s eligible=%s reason=%s "
            "next_strategy=%s client_id=%s",
            job.id,
            asset.id,
            decision.eligible,
            decision.reason,
            decision.next_strategy,
            client_id,
        )
        self._publish_fallback_event(
            job_id=job.id,
            asset_id=asset.id,
            event_type="fallback.evaluated",
            message="external fallback eligibility evaluated",
            error_code=None if decision.eligible else decision.reason,
            metadata=eval_metadata,
        )
        if not decision.eligible:
            self._bump_skipped()
            self._publish_fallback_event(
                job_id=job.id,
                asset_id=asset.id,
                event_type="fallback.skipped",
                message="external fallback skipped",
                error_code=decision.reason,
                metadata=eval_metadata,
            )
            return ExternalFallbackOutcome(skipped=True)

        if not (snapshot.provider or "").strip():
            self._publish_fallback_event(
                job_id=job.id,
                asset_id=asset.id,
                event_type="fallback.skipped",
                message="external fallback provider misconfigured",
                error_code="PROVIDER_MISCONFIGURED",
                metadata={**eval_metadata, "reason": "PROVIDER_MISCONFIGURED"},
                severity="ERROR",
            )
            return ExternalFallbackOutcome(
                result=self._technical(
                    job,
                    asset,
                    "EXTERNAL_PROVIDER_MISCONFIGURED",
                    "snapshot missing fallback_provider",
                    "unknown",
                    snapshot.model,
                    decision.reason,
                )
            )

        self._publish_fallback_event(
            job_id=job.id,
            asset_id=asset.id,
            event_type="fallback.started",
            message="external fallback started",
            metadata={
                **eval_metadata,
                "reason": decision.reason,
                "strategy": decision.next_strategy,
            },
        )
        logger.info(
            "fallback.started job_id=%s asset_id=%s reason=%s strategy=%s",
            job.id,
            asset.id,
            decision.reason,
            decision.next_strategy,
        )

        provider_name = (snapshot.provider or "").strip().lower()
        model_name = snapshot.model

        if self._cancelled():
            self._publish_fallback_event(
                job_id=job.id,
                asset_id=asset.id,
                event_type="fallback.cancelled",
                message="external fallback cancelled before provider call",
                error_code="JOB_CANCELLED",
                metadata=eval_metadata,
                severity="WARNING",
            )
            return ExternalFallbackOutcome(cancelled=True)

        key = build_external_idempotency_key(
            job_id=job.id,
            asset_id=asset.id,
            provider=provider_name,
            model=model_name,
            prompt_version=snapshot.prompt_version,
            configuration_snapshot_version=job.configuration_snapshot_version,
        )
        now = self.clock.now()
        claim = ExternalImageAnalysisRequest(
            id=str(uuid.uuid4()),
            idempotency_key=key,
            job_id=job.id,
            asset_id=asset.id,
            provider=provider_name,
            model=model_name,
            prompt_key=snapshot.prompt_key,
            prompt_version=snapshot.prompt_version,
            configuration_snapshot_version=job.configuration_snapshot_version,
            status=ExternalRequestStatus.CLAIMED,
            worker_token=worker_token,
            client_id=client_id,
            created_at=now,
            updated_at=now,
        )
        request = self.request_repo.try_claim(request=claim)

        recovery = self.recovery.decide(request)
        # Recovery C / prior success: already persisted position or active result.
        if recovery.action == "SKIP_PERSISTED":
            self._bump_skipped()
            self._publish_fallback_event(
                job_id=job.id,
                asset_id=asset.id,
                event_type="fallback.skipped",
                message="external fallback skipped; already persisted",
                error_code="SKIP_PERSISTED",
                metadata={**eval_metadata, "recovery_action": "SKIP_PERSISTED"},
            )
            return ExternalFallbackOutcome(skipped=True, request=request)

        # PERSISTED without position/active_result — never silent skip.
        if recovery.action == "RECONCILE_PERSISTED":
            logger.warning(
                "fallback.persisted_inconsistent job_id=%s asset_id=%s request_id=%s",
                job.id,
                asset.id,
                request.id,
            )
            if request.normalized_result:
                recovery = ExternalFallbackRecoveryDecision(
                    action="REUSE_NORMALIZED", request=request
                )
            else:
                request.status = ExternalRequestStatus.PERSISTENCE_PENDING
                request.updated_at = self.clock.now()
                self.request_repo.save(request)
                recovery = ExternalFallbackRecoveryDecision(action="CONTINUE", request=request)

        # Recovery B: reused normalized response without new provider call.
        if recovery.action == "REUSE_NORMALIZED":
            logger.info(
                "fallback.reconciled job_id=%s asset_id=%s request_id=%s reason=REUSE_NORMALIZED",
                job.id,
                asset.id,
                request.id,
            )
            result = self.recovery.result_from_stored(request, job, asset, decision.reason)
            attempt = self._ensure_attempt(
                job, asset, worker_token, provider_name, model_name, request
            )
            request.status = ExternalRequestStatus.PERSISTENCE_PENDING
            request.attempt_id = attempt.id
            request.updated_at = self.clock.now()
            self.request_repo.save(request)
            result.additional_fields["external_attempt_id"] = attempt.id
            result.additional_fields["external_request_id"] = request.id
            result.additional_fields["provider_call_status"] = "SUCCEEDED"
            result.additional_fields["persistence_status"] = "PENDING"
            if self.counters is not None:
                self.counters.fallback_requested += 1
            self._publish_fallback_event(
                job_id=job.id,
                asset_id=asset.id,
                event_type="fallback.provider_completed",
                message="reused normalized provider response; persistence pending",
                metadata={
                    **eval_metadata,
                    "recovery_action": "REUSE_NORMALIZED",
                    "provider_call_status": "SUCCEEDED",
                    "persistence_status": "PENDING",
                },
            )
            return ExternalFallbackOutcome(
                result=result,
                attempt=attempt,
                request=request,
                provider_call_status="SUCCEEDED",
                persistence_status="PENDING",
            )

        breaker = self._breaker_for(snapshot)
        if breaker is not None and breaker.is_open(provider_name, model_name or ""):
            if self.counters is not None:
                self.counters.external_failed += 1
            tech = self._technical(
                job,
                asset,
                "EXTERNAL_PROVIDER_CIRCUIT_OPEN",
                "External provider circuit breaker is open",
                provider_name,
                model_name,
                decision.reason,
            )
            self._publish_fallback_event(
                job_id=job.id,
                asset_id=asset.id,
                event_type="fallback.failed",
                message="external fallback failed; circuit breaker open",
                error_code="EXTERNAL_PROVIDER_CIRCUIT_OPEN",
                metadata=eval_metadata,
                severity="ERROR",
            )
            return ExternalFallbackOutcome(result=tech)

        if self.counters is not None:
            self.counters.fallback_requested += 1
            self.counters.fallback_in_progress += 1

        attempt = self._ensure_attempt(job, asset, worker_token, provider_name, model_name, request)
        request.status = ExternalRequestStatus.IN_FLIGHT
        request.attempt_id = attempt.id
        request.updated_at = self.clock.now()
        self.request_repo.save(request)

        try:
            if self._cancelled():
                return self._cancel_path(attempt, request)
            result, analysis, provider_call_status = self._execute_with_retries(
                job=job,
                asset=asset,
                snapshot=snapshot,
                provider_name=provider_name,
                model_name=model_name,
                eligibility_reason=decision.reason,
                client_id=client_id,
                request=request,
                breaker=breaker,
            )
        except Exception as exc:
            logger.exception("fallback.provider_failed job_id=%s asset_id=%s", job.id, asset.id)
            if breaker is not None:
                breaker.record_failure(provider_name, model_name or "")
            result = self._technical(
                job,
                asset,
                "EXTERNAL_PROVIDER_EXCEPTION",
                str(exc)[:500],
                provider_name,
                model_name,
                decision.reason,
            )
            provider_call_status = "FAILED"
            analysis = None

        if self._cancelled() and (result.additional_fields or {}).get("cancelled"):
            return self._cancel_path(attempt, request)

        # Persist durable normalized payload BEFORE closing attempt as success.
        self._store_provider_outcome(request, result, analysis, provider_call_status)
        result.additional_fields["external_attempt_id"] = attempt.id
        result.additional_fields["external_request_id"] = request.id
        result.additional_fields["provider_call_status"] = provider_call_status
        result.additional_fields["client_id"] = client_id

        if result.status is ImageResultStatus.RESOLVED_EXTERNAL:
            # Leave attempt STARTED / request PERSISTENCE_PENDING until caller persists.
            attempt.normalized_result = result.normalized_result
            attempt.validation_result = {
                "errors": list(result.validation_errors),
                "warnings": list(result.warnings),
            }
            attempt.extra = {
                **dict(attempt.extra or {}),
                "provider_call_status": "SUCCEEDED",
                "persistence_status": "PENDING",
                "estimated_cost": (result.additional_fields or {}).get("estimated_cost"),
                "request_image_sha256": request.request_image_sha256,
                "provider_response_sha256": request.provider_response_sha256,
                "normalized_result_sha256": request.normalized_result_sha256,
                "prompt_version": snapshot.prompt_version,
                "client_id": client_id,
            }
            if request.provider_response_sha256:
                attempt.raw_result_reference = request.provider_response_sha256
            self.attempt_repo.save(attempt)
            result.additional_fields["persistence_status"] = "PENDING"
            if self.counters is not None:
                self.counters.fallback_in_progress = max(0, self.counters.fallback_in_progress - 1)
            self._publish_fallback_event(
                job_id=job.id,
                asset_id=asset.id,
                event_type="fallback.provider_completed",
                message="external provider response ready; persistence pending",
                metadata={
                    **eval_metadata,
                    "status": getattr(result.status, "value", str(result.status)),
                    "provider_call_status": provider_call_status,
                    "persistence_status": "PENDING",
                },
            )
            return ExternalFallbackOutcome(
                result=result,
                attempt=attempt,
                request=request,
                provider_call_status=provider_call_status,
                persistence_status="PENDING",
            )

        # Non-resolved: provider finished but no durable position — terminal failed.
        self._close_attempt_terminal(attempt, result, request)
        self._update_counters(result)
        if self.counters is not None:
            self.counters.fallback_in_progress = max(0, self.counters.fallback_in_progress - 1)
        self._publish_fallback_event(
            job_id=job.id,
            asset_id=asset.id,
            event_type="fallback.failed",
            message="external fallback finished without durable resolve",
            error_code=result.error_code,
            metadata={
                **eval_metadata,
                "status": getattr(result.status, "value", str(result.status)),
                "provider_call_status": provider_call_status,
                "persistence_status": "NOT_APPLICABLE",
                "requested_model": snapshot.model,
                "executed_model": result.model_name
                or (result.additional_fields or {}).get("executed_model"),
                "provider_declared_no_result": bool(
                    (result.additional_fields or {}).get("provider_declared_no_result")
                ),
            },
            severity="ERROR",
        )
        return ExternalFallbackOutcome(
            result=result,
            attempt=attempt,
            request=request,
            provider_call_status=provider_call_status,
            persistence_status="NOT_APPLICABLE",
        )

    def finalize_after_persist(
        self,
        *,
        attempt: ProcessingAttempt,
        request: ExternalImageAnalysisRequest | None,
        result: ImageProcessingResult,
        position_id: str | None,
        active_result_id: str | None,
        persisted: bool,
    ) -> None:
        """Mark attempt SUCCEEDED only when a position exists (persisted or reconciled).

        ``fallback.completed`` is published only from this durable boundary.
        """
        self._publish_fallback_event(
            job_id=attempt.job_id,
            asset_id=attempt.asset_id,
            event_type="fallback.persistence_started",
            message="external fallback persistence started",
            metadata={
                "asset_id": attempt.asset_id,
                "attempt_id": attempt.id,
                "persisted": persisted,
                "position_id": position_id,
                "active_result_id": active_result_id,
            },
        )
        now = self.clock.now()
        if result.status is ImageResultStatus.RESOLVED_EXTERNAL and (
            persisted or position_id or active_result_id
        ):
            attempt.status = ProcessingAttemptStatus.SUCCEEDED
            attempt.error_code = None
            attempt.error_message = None
            attempt.extra = {
                **dict(attempt.extra or {}),
                "provider_call_status": "SUCCEEDED",
                "persistence_status": "SUCCEEDED",
                "position_id": position_id,
                "active_result_id": active_result_id,
            }
            if request is not None:
                request.status = ExternalRequestStatus.PERSISTED
                request.position_id = position_id
                request.active_result_id = active_result_id
                request.updated_at = now
                self.request_repo.save(request)
            if self.counters is not None:
                self.counters.resolved_external += 1
            logger.info(
                "fallback.persisted job_id=%s asset_id=%s attempt_id=%s position_id=%s",
                attempt.job_id,
                attempt.asset_id,
                attempt.id,
                position_id,
            )
        else:
            attempt.status = ProcessingAttemptStatus.FAILED_TECHNICAL
            attempt.error_code = result.error_code or "PROCESSING_PERSISTENCE_FAILED"
            attempt.error_message = result.error_message
            attempt.extra = {
                **dict(attempt.extra or {}),
                "provider_call_status": "SUCCEEDED",
                "persistence_status": "FAILED",
            }
            if request is not None:
                request.status = ExternalRequestStatus.PERSISTENCE_PENDING
                request.error_code = attempt.error_code
                request.error_message = attempt.error_message
                request.updated_at = now
                self.request_repo.save(request)
            if self.counters is not None:
                self.counters.external_failed += 1
            logger.warning(
                "fallback.persistence_failed job_id=%s asset_id=%s attempt_id=%s",
                attempt.job_id,
                attempt.asset_id,
                attempt.id,
            )
        attempt.finished_at = now
        if attempt.started_at is not None:
            attempt.duration_ms = int((now - attempt.started_at).total_seconds() * 1000)
        attempt.normalized_result = result.normalized_result
        self.attempt_repo.save(attempt)

        durable = result.status is ImageResultStatus.RESOLVED_EXTERNAL and (
            persisted or position_id or active_result_id
        )
        self._publish_fallback_event(
            job_id=attempt.job_id,
            asset_id=attempt.asset_id,
            event_type="fallback.completed" if durable else "fallback.failed",
            message=(
                "external fallback persisted"
                if durable
                else "external fallback persistence failed"
            ),
            error_code=None if durable else (attempt.error_code or "PROCESSING_PERSISTENCE_FAILED"),
            metadata={
                "asset_id": attempt.asset_id,
                "position_id": position_id,
                "active_result_id": active_result_id,
                "persisted": persisted,
                "persistence_status": "SUCCEEDED" if durable else "FAILED",
                "status": getattr(result.status, "value", str(result.status)),
            },
            severity="INFO" if durable else "ERROR",
        )

    def _execute_with_retries(
        self,
        *,
        job: Job,
        asset: SourceAsset,
        snapshot: ExternalFallbackSnapshot,
        provider_name: str,
        model_name: str | None,
        eligibility_reason: str,
        client_id: str | None,
        request: ExternalImageAnalysisRequest,
        breaker: ExternalCircuitBreaker | None,
    ) -> tuple[ImageProcessingResult, ExternalAnalysisResult | None, str]:
        provider = self._resolve_provider(snapshot, provider_name, model_name)
        if provider.provider_name.strip().lower() != provider_name:
            raise ValueError(
                f"snapshot provider {provider_name!r} != executed {provider.provider_name!r}"
            )
        executed_model = provider.model_name
        if (
            model_name
            and executed_model
            and model_name.strip()
            not in (
                executed_model,
                "default",
            )
        ):
            if (model_name or "").strip() and (executed_model or "").strip():
                if model_name.strip().lower() != executed_model.strip().lower():
                    raise ValueError(
                        "EXTERNAL_PROVIDER_MODEL_MISMATCH: "
                        f"snapshot model {model_name!r} != executed {executed_model!r}"
                    )

        limiter = self.concurrency_limiter or ExternalConcurrencyLimiter(snapshot.max_concurrency)
        last_analysis: ExternalAnalysisResult | None = None
        max_attempts = max(1, int(snapshot.max_attempts))

        for attempt_idx in range(1, max_attempts + 1):
            if self._cancelled():
                return (
                    self._cancelled_image_result(
                        job, asset, provider_name, model_name, eligibility_reason
                    ),
                    None,
                    "CANCELLED",
                )
            if breaker is not None and not breaker.try_acquire_call(
                provider_name, model_name or ""
            ):
                return (
                    self._technical(
                        job,
                        asset,
                        "EXTERNAL_PROVIDER_CIRCUIT_OPEN",
                        "Circuit open / half-open probe busy",
                        provider_name,
                        model_name,
                        eligibility_reason,
                    ),
                    None,
                    "CIRCUIT_OPEN",
                )

            with limiter.acquire(timeout=snapshot.timeout_seconds) as acquired:
                if not acquired:
                    return (
                        self._technical(
                            job,
                            asset,
                            "EXTERNAL_CONCURRENCY_TIMEOUT",
                            "Could not acquire external concurrency slot",
                            provider_name,
                            model_name,
                            eligibility_reason,
                        ),
                        None,
                        "FAILED",
                    )
                if self._cancelled():
                    return (
                        self._cancelled_image_result(
                            job, asset, provider_name, model_name, eligibility_reason
                        ),
                        None,
                        "CANCELLED",
                    )
                content = self.content_reader(asset)
                request_image_sha256_raw = hashlib.sha256(content).hexdigest()
                request.request_image_sha256 = request_image_sha256_raw
                self._publish_fallback_event(
                    job_id=job.id,
                    asset_id=asset.id,
                    event_type="fallback.provider_call_started",
                    message="external provider call started",
                    metadata={
                        "provider": provider_name,
                        "requested_model": model_name,
                        "attempt_number": attempt_idx,
                        "request_image_sha256": request_image_sha256_raw,
                        "request_image_sha256_raw": request_image_sha256_raw,
                        "request_image_bytes": len(content),
                    },
                )
                analysis = provider.analyze_image(
                    ExternalImageInput(
                        content=content,
                        mime_type=getattr(asset, "content_type", None) or "image/jpeg",
                        asset_id=asset.id,
                        original_filename=getattr(asset, "original_filename", None),
                    ),
                    ExternalAnalysisContext(
                        job_id=job.id,
                        asset_id=asset.id,
                        client_id=client_id,
                        prompt_key=snapshot.prompt_key,
                        prompt_version=snapshot.prompt_version,
                        timeout_seconds=snapshot.timeout_seconds,
                        max_image_dimension=snapshot.max_image_dimension,
                        quantity_max=snapshot.quantity_max,
                        configuration_snapshot_version=job.configuration_snapshot_version,
                        extra={"client_rules": snapshot.client_rules or {}},
                    ),
                )
                last_analysis = analysis
                self._publish_fallback_event(
                    job_id=job.id,
                    asset_id=asset.id,
                    event_type="fallback.provider_call_completed",
                    message="external provider call completed",
                    error_code=analysis.error_code
                    if analysis.status
                    in (
                        ExternalAnalysisStatus.FAILED_TECHNICAL,
                        ExternalAnalysisStatus.TIMEOUT,
                        ExternalAnalysisStatus.RATE_LIMITED,
                    )
                    else None,
                    metadata={
                        "provider": analysis.provider_name or provider_name,
                        "requested_model": model_name,
                        "executed_model": analysis.model_name,
                        "attempt_number": attempt_idx,
                        "analysis_status": analysis.status.value,
                        "duration_ms": analysis.duration_ms,
                        "parse_status": (analysis.additional_fields or {}).get("parse_status"),
                        "normalized_code_present": bool(analysis.internal_code),
                        "normalized_quantity_present": analysis.quantity is not None,
                        "provider_response_sha256": analysis.raw_reference
                        or (analysis.additional_fields or {}).get("provider_response_sha256"),
                        # Stable alias: always the raw asset bytes for this call.
                        "request_image_sha256": request_image_sha256_raw,
                        "request_image_sha256_raw": request_image_sha256_raw,
                        "request_image_sha256_prepared": (analysis.additional_fields or {}).get(
                            "request_image_sha256_prepared"
                        )
                        or (analysis.additional_fields or {}).get("request_image_sha256"),
                        "schema_validation": (analysis.additional_fields or {}).get(
                            "schema_validation"
                        ),
                        "adapter_name": (analysis.additional_fields or {}).get("adapter_name"),
                        "schema_version": (analysis.additional_fields or {}).get("schema_version"),
                    },
                    severity=(
                        "ERROR"
                        if analysis.status
                        in (
                            ExternalAnalysisStatus.FAILED_TECHNICAL,
                            ExternalAnalysisStatus.TIMEOUT,
                            ExternalAnalysisStatus.RATE_LIMITED,
                        )
                        else "INFO"
                    ),
                )

            if analysis.status in _RETRYABLE_ANALYSIS:
                if breaker is not None:
                    breaker.record_failure(provider_name, model_name or "")
                if attempt_idx < max_attempts:
                    time.sleep(min(2.0, float(snapshot.retry_backoff_seconds) * attempt_idx))
                    continue
            else:
                if breaker is not None:
                    if analysis.status in (
                        ExternalAnalysisStatus.VALID,
                        ExternalAnalysisStatus.INVALID,
                        ExternalAnalysisStatus.AMBIGUOUS,
                        ExternalAnalysisStatus.NO_RESULT,
                    ):
                        breaker.record_success(provider_name, model_name or "")
                    else:
                        breaker.record_failure(provider_name, model_name or "")

            result = self.normalizer.normalize(
                job_id=job.id,
                asset_id=asset.id,
                analysis=analysis,
                quantity_max=snapshot.quantity_max,
                client_rules=snapshot.client_rules,
                client_id=client_id,
                supplier_extraction_profile=snapshot.supplier_extraction_profile,
                profile_aware_validation_enabled=snapshot.profile_aware_validation_enabled,
            )
            result.additional_fields["fallback_eligible"] = True
            result.additional_fields["fallback_reason"] = eligibility_reason
            result.additional_fields["external_provider"] = provider_name
            result.additional_fields["external_model"] = analysis.model_name or model_name
            result.provider_name = provider_name
            result.model_name = analysis.model_name or model_name
            call_status = (
                "SUCCEEDED"
                if analysis.status
                not in (
                    ExternalAnalysisStatus.TIMEOUT,
                    ExternalAnalysisStatus.RATE_LIMITED,
                    ExternalAnalysisStatus.FAILED_TECHNICAL,
                )
                else "FAILED"
            )
            return result, analysis, call_status

        assert last_analysis is not None
        result = self.normalizer.normalize(
            job_id=job.id,
            asset_id=asset.id,
            analysis=last_analysis,
            quantity_max=snapshot.quantity_max,
            client_rules=snapshot.client_rules,
            client_id=client_id,
            supplier_extraction_profile=snapshot.supplier_extraction_profile,
            profile_aware_validation_enabled=snapshot.profile_aware_validation_enabled,
        )
        result.additional_fields["fallback_eligible"] = True
        result.additional_fields["fallback_reason"] = eligibility_reason
        return result, last_analysis, "FAILED"

    def _resolve_provider(
        self,
        snapshot: ExternalFallbackSnapshot,
        provider_name: str,
        model_name: str | None,
    ) -> ExternalImageAnalysisProvider:
        if self.provider is not None:
            return self.provider
        return self.provider_factory.resolve(provider=provider_name, model=model_name)

    def _breaker_for(self, snapshot: ExternalFallbackSnapshot) -> ExternalCircuitBreaker | None:
        if self.circuit_breaker is not None:
            return self.circuit_breaker
        return ExternalCircuitBreaker(
            failure_threshold=snapshot.circuit_breaker_threshold,
            cooldown_seconds=snapshot.circuit_breaker_cooldown_seconds,
            profile=f"snap-v{snapshot.snapshot_version}",
        )

    def _ensure_attempt(
        self,
        job: Job,
        asset: SourceAsset,
        worker_token: str,
        provider_name: str,
        model_name: str | None,
        request: ExternalImageAnalysisRequest,
    ) -> ProcessingAttempt:
        if request.attempt_id:
            existing = self.attempt_repo.get_by_id(request.attempt_id)
            if existing is not None and existing.status is ProcessingAttemptStatus.STARTED:
                return existing
        return self.attempt_repo.create_next_attempt(
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

    def _store_provider_outcome(
        self,
        request: ExternalImageAnalysisRequest,
        result: ImageProcessingResult,
        analysis: ExternalAnalysisResult | None,
        provider_call_status: str,
    ) -> None:
        now = self.clock.now()
        request.normalized_result = result.normalized_result
        request.validation_result = {
            "errors": list(result.validation_errors),
            "warnings": list(result.warnings),
        }
        if analysis is not None:
            request.usage = analysis.usage
            request.estimated_cost = analysis.estimated_cost
            request.confidence = analysis.confidence
            request.duration_ms = analysis.duration_ms
            # Keep request_image_sha256 as the raw asset hash set at call start.
            # Provider response hash (not the image bytes).
            response_sha = analysis.raw_reference or (analysis.additional_fields or {}).get(
                "provider_response_sha256"
            )
            if isinstance(response_sha, str) and response_sha:
                request.provider_response_sha256 = response_sha
            elif analysis.normalized_result is not None:
                request.provider_response_sha256 = hashlib.sha256(
                    json.dumps(analysis.normalized_result, sort_keys=True).encode()
                ).hexdigest()
            if analysis.model_name:
                request.model = analysis.model_name
            if analysis.provider_name:
                request.provider = analysis.provider_name
            if analysis.prompt_version:
                request.prompt_version = analysis.prompt_version
            prompt_key = (analysis.additional_fields or {}).get("prompt_key")
            if isinstance(prompt_key, str) and prompt_key.strip():
                request.prompt_key = prompt_key.strip()
        if result.normalized_result is not None:
            request.normalized_result_sha256 = hashlib.sha256(
                json.dumps(result.normalized_result, sort_keys=True).encode()
            ).hexdigest()
        if result.status is ImageResultStatus.RESOLVED_EXTERNAL:
            request.status = ExternalRequestStatus.PERSISTENCE_PENDING
        elif result.status is ImageResultStatus.PENDING_MANUAL_REVIEW:
            request.status = ExternalRequestStatus.VALIDATION_FAILED
        elif result.status is ImageResultStatus.UNRECOGNIZED:
            request.status = ExternalRequestStatus.FAILED_FINAL
        elif provider_call_status == "FAILED":
            request.status = ExternalRequestStatus.FAILED_RETRYABLE
        else:
            request.status = ExternalRequestStatus.FAILED_FINAL
        request.error_code = result.error_code
        request.error_message = result.error_message
        request.updated_at = now
        self.request_repo.save(request)

    def _result_from_stored(
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

    def _close_attempt_terminal(
        self,
        attempt: ProcessingAttempt,
        result: ImageProcessingResult,
        request: ExternalImageAnalysisRequest,
    ) -> None:
        now = self.clock.now()
        if (result.additional_fields or {}).get("cancelled"):
            attempt.status = ProcessingAttemptStatus.CANCELLED
            request.status = ExternalRequestStatus.CANCELLED
        else:
            attempt.status = {
                ImageResultStatus.UNRECOGNIZED: ProcessingAttemptStatus.UNRECOGNIZED,
                ImageResultStatus.FAILED_TECHNICAL: ProcessingAttemptStatus.FAILED_TECHNICAL,
                ImageResultStatus.PENDING_MANUAL_REVIEW: ProcessingAttemptStatus.INVALID,
            }.get(result.status, ProcessingAttemptStatus.FAILED_TECHNICAL)
        attempt.finished_at = now
        if attempt.started_at is not None:
            attempt.duration_ms = int((now - attempt.started_at).total_seconds() * 1000)
        attempt.error_code = result.error_code
        attempt.error_message = result.error_message
        attempt.normalized_result = result.normalized_result
        attempt.validation_result = {
            "errors": list(result.validation_errors),
            "warnings": list(result.warnings),
        }
        attempt.extra = {
            **dict(attempt.extra or {}),
            "provider_call_status": (result.additional_fields or {}).get("provider_call_status"),
            "persistence_status": "NOT_APPLICABLE",
            "request_image_sha256": request.request_image_sha256,
            "provider_response_sha256": request.provider_response_sha256,
            "normalized_result_sha256": request.normalized_result_sha256,
        }
        if request.provider_response_sha256:
            attempt.raw_result_reference = request.provider_response_sha256
        self.attempt_repo.save(attempt)
        request.updated_at = now
        self.request_repo.save(request)

    def _cancel_path(
        self, attempt: ProcessingAttempt, request: ExternalImageAnalysisRequest
    ) -> ExternalFallbackOutcome:
        now = self.clock.now()
        attempt.status = ProcessingAttemptStatus.CANCELLED
        attempt.finished_at = now
        attempt.error_code = "JOB_CANCELLED"
        attempt.error_message = "Job cancelled during external fallback"
        self.attempt_repo.save(attempt)
        request.status = ExternalRequestStatus.CANCELLED
        request.updated_at = now
        self.request_repo.save(request)
        if self.counters is not None:
            self.counters.fallback_in_progress = max(0, self.counters.fallback_in_progress - 1)
        self._publish_fallback_event(
            job_id=attempt.job_id,
            asset_id=attempt.asset_id,
            event_type="fallback.cancelled",
            message="external fallback cancelled",
            error_code="JOB_CANCELLED",
            metadata={
                "asset_id": attempt.asset_id,
                "attempt_id": attempt.id,
                "request_id": request.id,
            },
            severity="WARNING",
        )
        return ExternalFallbackOutcome(cancelled=True, attempt=attempt, request=request)

    def _update_counters(self, result: ImageProcessingResult) -> None:
        if self.counters is None:
            return
        if (result.additional_fields or {}).get("cancelled"):
            return
        cost = (result.additional_fields or {}).get("estimated_cost")
        if isinstance(cost, (int, float)):
            self.counters.estimated_external_cost += float(cost)
        if result.status is ImageResultStatus.UNRECOGNIZED:
            self.counters.external_unrecognized += 1
        elif result.status is ImageResultStatus.FAILED_TECHNICAL:
            self.counters.external_failed += 1
        elif result.status is ImageResultStatus.PENDING_MANUAL_REVIEW:
            self.counters.pending_manual_review += 1

    def _bump_skipped(self) -> None:
        if self.counters is not None:
            self.counters.fallback_skipped += 1

    def _cancelled(self) -> bool:
        return bool(self.is_cancelled and self.is_cancelled())

    def _cancelled_image_result(
        self,
        job: Job,
        asset: SourceAsset,
        provider_name: str,
        model_name: str | None,
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

    def _technical(
        self,
        job: Job,
        asset: SourceAsset,
        error_code: str,
        message: str,
        provider_name: str,
        model_name: str | None,
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
                "fallback_eligible": True,
                "fallback_reason": reason,
                "external_provider": provider_name,
                "external_model": model_name,
            },
            provider_name=provider_name,
            model_name=model_name,
            error_code=error_code,
            error_message=message[:500],
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
    retry_backoff_seconds: float = 0.5,
    ambiguous_internal_code_fallback_enabled: bool = False,
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
        "retry_backoff_seconds": float(retry_backoff_seconds),
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
        "ambiguous_internal_code_fallback_enabled": bool(ambiguous_internal_code_fallback_enabled),
    }


def aggregate_fallback_progress_from_requests(
    requests: list[ExternalImageAnalysisRequest],
    *,
    resolved_internal: int = 0,
) -> dict[str, Any]:
    """Derive public counters from durable request rows (worker-restart safe)."""
    counters = FallbackProgressCounters(resolved_internal=resolved_internal)
    for req in requests:
        if req.status is ExternalRequestStatus.CANCELLED:
            continue
        if req.status is ExternalRequestStatus.CLAIMED:
            counters.fallback_skipped += 1
            continue
        counters.fallback_requested += 1
        if req.status is ExternalRequestStatus.IN_FLIGHT:
            counters.fallback_in_progress += 1
        elif req.status is ExternalRequestStatus.PERSISTED:
            counters.resolved_external += 1
        elif req.status is ExternalRequestStatus.VALIDATION_FAILED:
            counters.pending_manual_review += 1
        elif req.status in (
            ExternalRequestStatus.FAILED_FINAL,
            ExternalRequestStatus.FAILED_RETRYABLE,
            ExternalRequestStatus.PERSISTENCE_PENDING,
        ):
            if req.status is ExternalRequestStatus.PERSISTENCE_PENDING and req.normalized_result:
                # Still awaiting persist — count as in-progress style pending, not external_failed.
                counters.fallback_in_progress += 1
            else:
                counters.external_failed += 1
        if isinstance(req.estimated_cost, (int, float)):
            counters.estimated_external_cost += float(req.estimated_cost)
    return counters.to_public_dict()


def sanitize_fallback_asset_summaries(
    requests: list[ExternalImageAnalysisRequest],
) -> list[dict[str, Any]]:
    """Public per-asset fallback rows (no secrets / raw payloads)."""
    out: list[dict[str, Any]] = []
    for r in requests:
        if r.status is ExternalRequestStatus.CANCELLED:
            continue
        norm = r.normalized_result if isinstance(r.normalized_result, dict) else {}
        validation = r.validation_result if isinstance(r.validation_result, dict) else {}
        if r.status is ExternalRequestStatus.PERSISTED:
            persistence_status = "SUCCEEDED"
        elif r.status is ExternalRequestStatus.PERSISTENCE_PENDING:
            persistence_status = "PENDING"
        elif r.status in (
            ExternalRequestStatus.FAILED_FINAL,
            ExternalRequestStatus.FAILED_RETRYABLE,
        ):
            persistence_status = "FAILED"
        else:
            persistence_status = None
        out.append(
            {
                "asset_id": r.asset_id,
                "fallback_status": r.status.value,
                "external_provider": r.provider,
                "external_model": r.model,
                "requested_model": r.model,
                "executed_model": r.model,
                "prompt_key": r.prompt_key,
                "prompt_version": r.prompt_version,
                "external_attempt_id": r.attempt_id,
                "external_duration_ms": r.duration_ms,
                "estimated_cost": r.estimated_cost,
                "internal_code": norm.get("internal_code"),
                "quantity": norm.get("quantity"),
                "validation_errors": list(validation.get("errors") or []),
                "warnings": list(validation.get("warnings") or []),
                "persistence_status": persistence_status,
                "position_id": r.position_id,
                "active_result_id": r.active_result_id,
                "error_code": r.error_code,
                "error_message": (r.error_message or "")[:200] or None,
                "provider_response_sha256": r.provider_response_sha256,
                "request_image_sha256": r.request_image_sha256,
            }
        )
    return out


def resolve_fallback_progress_payload(
    *,
    job_id: str,
    external_fallback: Any,
    external_request_repo: Any,
    resolved_internal: int = 0,
) -> dict[str, Any]:
    """Prefer durable DB aggregates; fall back to process-local counters."""
    payload: dict[str, Any] = {}
    if external_fallback is None:
        return payload
    if external_request_repo is not None:
        try:
            req_rows = list(external_request_repo.list_by_job(job_id))
            payload["fallback_progress"] = aggregate_fallback_progress_from_requests(
                req_rows, resolved_internal=resolved_internal
            )
            payload["fallback_asset_summaries"] = sanitize_fallback_asset_summaries(req_rows)
            return payload
        except Exception:
            logger.warning("fallback.progress_aggregate_failed job_id=%s", job_id, exc_info=True)
    counters = getattr(external_fallback, "counters", None)
    if counters is not None:
        payload["fallback_progress"] = counters.to_public_dict()
    return payload


__all__ = [
    "ExternalFallbackOutcome",
    "ExternalFallbackSnapshot",
    "ExternalProviderFallbackOrchestrator",
    "ExternalProviderFactory",
    "FallbackProgressCounters",
    "aggregate_fallback_progress_from_requests",
    "build_external_fallback_snapshot_dict",
    "resolve_fallback_progress_payload",
    "sanitize_fallback_asset_summaries",
]
