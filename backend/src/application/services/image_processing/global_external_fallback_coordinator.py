"""GLOBAL_BATCH coordinator — orchestration only (after internal aisle pass).

Delegates eligibility, batching, journal, schema validation, merge plan/apply, outcome.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.application.ports.global_fallback_batch_request_repository import (
    GlobalFallbackBatchRequestRepository,
)
from src.application.services.image_processing.external_fallback_mode import (
    EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH,
    EXTERNAL_FALLBACK_MODE_PER_ASSET,
    GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
    GLOBAL_FALLBACK_EXECUTION_SCOPE,
    GLOBAL_FALLBACK_PROMPT_KEY,
    GLOBAL_FALLBACK_SCHEMA_VERSION,
    GLOBAL_FALLBACK_STRATEGY_KEY,
    PER_ASSET_DEPRECATION_NOTE,
    parse_external_fallback_mode,
)
from src.application.services.image_processing.global_fallback_batching import (
    AssetOrderKey,
    GlobalFallbackBatchSlice,
    build_batch_slices,
)
from src.application.services.image_processing.global_fallback_eligibility import (
    evaluate_global_fallback_eligibility,
)
from src.application.services.image_processing.global_fallback_fingerprints import (
    asset_content_identity_hash,
    prompt_fingerprint_from_parts,
)
from src.application.services.image_processing.global_fallback_merge_applier import (
    GlobalFallbackMergeApplier,
)
from src.application.services.image_processing.global_fallback_merge_planner import (
    build_merge_plan,
)
from src.application.services.image_processing.global_fallback_merge_policy import (
    GlobalFallbackMergeDecision,
    InternalAssetEvidence,
)
from src.application.services.image_processing.global_fallback_outcome_policy import (
    GlobalFallbackOutcomeSeverity,
    decide_global_fallback_outcome,
)
from src.application.services.image_processing.global_fallback_schema_validation import (
    GlobalFallbackSchemaError,
    validate_global_fallback_report,
)
from src.domain.assets.entities import SourceAsset
from src.domain.image_processing.contracts import ExecutionScope
from src.domain.image_processing.global_fallback_batch_request import (
    GlobalFallbackBatchRequest,
    GlobalFallbackBatchStatus,
    sanitize_entities_for_storage,
)
from src.domain.image_processing.job_processing_lease import JobProcessingLease

logger = logging.getLogger(__name__)


class GlobalFallbackBatchAnalyzer(Protocol):
    def analyze_batch(
        self,
        *,
        job: Any,
        aisle: Any,
        assets: Sequence[SourceAsset],
        batch: GlobalFallbackBatchSlice,
        snapshot: Any,
        prompt_fingerprint: str,
    ) -> GlobalFallbackBatchAnalysisResult: ...


@dataclass
class GlobalFallbackBatchAnalysisResult:
    ok: bool
    entities: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str | None = None
    prompt_key: str | None = None
    prompt_fingerprint: str | None = None
    effective_prompt_text: str | None = None
    provider: str | None = None
    model: str | None = None
    estimated_cost: float | None = None
    prompt_tokens: int | None = None
    response_tokens: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_report: dict[str, Any] | None = None
    duration_ms: int | None = None
    frame_to_asset_map: dict[str, str] = field(default_factory=dict)
    prepared_image_hashes: dict[str, str] = field(default_factory=dict)


@dataclass
class GlobalFallbackCoordinatorResult:
    skipped: bool = False
    skip_reason: str | None = None
    cancelled: bool = False
    failed: bool = False
    error_code: str | None = None
    error_message: str | None = None
    outcome_severity: str | None = None
    requests_count: int = 0
    batch_count: int = 0
    entity_count: int = 0
    conflict_count: int = 0
    applied_external: int = 0
    kept_internal: int = 0
    unmapped_count: int = 0
    decisions: list[GlobalFallbackMergeDecision] = field(default_factory=list)
    public_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class GlobalExternalFallbackCoordinator:
    lease_repo: Any
    clock: Any
    batch_analyzer: GlobalFallbackBatchAnalyzer
    batch_journal: GlobalFallbackBatchRequestRepository
    merge_applier: GlobalFallbackMergeApplier
    persist_job_summary: Callable[[str, dict[str, Any]], None]
    event_publisher: Any | None = None
    lease_duration_seconds: int = 600
    max_frames_per_batch: int = 48
    filename_to_asset_id: Callable[[Sequence[SourceAsset]], dict[str, str]] | None = None

    def process_after_internal_pass(
        self,
        *,
        job: Any,
        aisle: Any,
        assets: Sequence[SourceAsset],
        snapshot: Any,
        worker_token: str,
        is_cancelled: Callable[[], bool],
        evidence_by_asset: Mapping[str, InternalAssetEvidence],
        configuration_fingerprint: str,
        prompt_fingerprint: str | None = None,
        execution_id: str | None = None,
        order_keys: Sequence[AssetOrderKey] | None = None,
        prepared_image_hashes_by_asset: dict[str, str] | None = None,
    ) -> GlobalFallbackCoordinatorResult:
        if snapshot is None or not bool(getattr(snapshot, "enabled", False)):
            return GlobalFallbackCoordinatorResult(
                skipped=True, skip_reason="fallback_disabled"
            )

        try:
            mode = parse_external_fallback_mode(getattr(snapshot, "fallback_mode", None))
        except Exception as exc:
            return GlobalFallbackCoordinatorResult(
                failed=True,
                error_code="EXTERNAL_FALLBACK_MODE_INVALID",
                error_message=str(exc)[:500],
                outcome_severity=GlobalFallbackOutcomeSeverity.FAILED_CONFIGURATION.value,
            )

        if mode == EXTERNAL_FALLBACK_MODE_PER_ASSET:
            logger.warning(
                "global_fallback.per_asset_deprecated job_id=%s note=%s",
                job.id,
                PER_ASSET_DEPRECATION_NOTE,
            )
            return GlobalFallbackCoordinatorResult(
                skipped=True, skip_reason="mode_per_asset"
            )
        if mode != EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH:
            return GlobalFallbackCoordinatorResult(
                failed=True,
                error_code="EXTERNAL_FALLBACK_MODE_INVALID",
                error_message=f"Unexpected fallback_mode={mode}",
                outcome_severity=GlobalFallbackOutcomeSeverity.FAILED_CONFIGURATION.value,
            )

        if is_cancelled():
            return GlobalFallbackCoordinatorResult(cancelled=True, skip_reason="cancelled")

        eligible_assets = [a for a in assets if a is not None and getattr(a, "id", None)]
        if not eligible_assets:
            return GlobalFallbackCoordinatorResult(
                skipped=True, skip_reason="no_eligible_assets"
            )

        eligibility = evaluate_global_fallback_eligibility(evidence_by_asset)
        self._emit(
            job.id,
            "fallback.batch_evaluated",
            message=eligibility.reason,
            metadata={
                "fallback_mode": mode,
                "needs_fallback": eligibility.needs_fallback,
                "resolved_internal": eligibility.resolved_internal,
                "eligible_count": eligibility.eligible_count,
                "total_assets": eligibility.total_assets,
            },
        )
        if not eligibility.needs_fallback:
            summary = {
                "fallback_mode": mode,
                "needs_fallback": False,
                "skip_reason": eligibility.reason,
                "requests_count": 0,
                "images_sent": 0,
                "batch_count": 0,
                "persistence_status": "SKIPPED",
            }
            self.persist_job_summary(job.id, summary)
            return GlobalFallbackCoordinatorResult(
                skipped=True,
                skip_reason=eligibility.reason,
                public_summary=summary,
            )

        if getattr(snapshot, "supplier_prompt_required", False):
            sp = getattr(snapshot, "supplier_prompt", None)
            content = ""
            if isinstance(sp, dict):
                content = str(sp.get("content") or sp.get("instructions_text") or "")
            if not content.strip():
                outcome = decide_global_fallback_outcome(
                    eligibility=eligibility,
                    configuration_error=True,
                    configuration_code="SUPPLIER_PROMPT_REQUIRED",
                    configuration_message="supplier instructions_text required",
                )
                return GlobalFallbackCoordinatorResult(
                    failed=outcome.fail_job,
                    error_code=outcome.error_code,
                    error_message=outcome.message,
                    outcome_severity=outcome.severity.value,
                )

        if not configuration_fingerprint:
            return GlobalFallbackCoordinatorResult(
                failed=True,
                error_code="CONFIGURATION_FINGERPRINT_REQUIRED",
                error_message="configuration_fingerprint required",
                outcome_severity=GlobalFallbackOutcomeSeverity.FAILED_CONFIGURATION.value,
            )

        hashes = prepared_image_hashes_by_asset or {
            a.id: asset_content_identity_hash(
                asset_id=a.id,
                storage_key=getattr(a, "storage_key", None),
                etag=getattr(a, "etag", None),
                file_size_bytes=getattr(a, "file_size_bytes", None),
                mime_type=getattr(a, "mime_type", None),
            )
            for a in eligible_assets
        }
        pf = prompt_fingerprint or self._default_prompt_fingerprint(snapshot)
        exec_id = str(
            execution_id
            or getattr(job, "execution_id", None)
            or job.id
        )

        try:
            slices = build_batch_slices(
                [a.id for a in eligible_assets],
                max_per_batch=int(self.max_frames_per_batch),
                job_id=job.id,
                execution_id=exec_id,
                attempt=int(getattr(job, "attempt_count", 1) or 1),
                fallback_mode=mode,
                provider=str(getattr(snapshot, "provider", "") or ""),
                model=getattr(snapshot, "model", None),
                schema_version=GLOBAL_FALLBACK_SCHEMA_VERSION,
                configuration_fingerprint=configuration_fingerprint,
                prompt_fingerprint=pf,
                prepared_image_hashes_by_asset=hashes,
                order_keys=order_keys,
            )
        except ValueError as exc:
            return GlobalFallbackCoordinatorResult(
                failed=True,
                error_code="FINGERPRINT_INVALID",
                error_message=str(exc)[:500],
                outcome_severity=GlobalFallbackOutcomeSeverity.FAILED_CONFIGURATION.value,
            )

        asset_by_id = {a.id: a for a in eligible_assets}
        name_map = (
            self.filename_to_asset_id(eligible_assets)
            if self.filename_to_asset_id is not None
            else {}
        )

        lease = self._acquire_lease(job.id, worker_token)
        if lease is None:
            return GlobalFallbackCoordinatorResult(
                skipped=True, skip_reason="lease_not_acquired"
            )

        result = GlobalFallbackCoordinatorResult(batch_count=len(slices))
        batch_summaries: list[dict[str, Any]] = []
        total_cost = 0.0
        total_prompt_tokens = 0
        total_response_tokens = 0
        total_duration = 0

        try:
            for batch in slices:
                if is_cancelled():
                    self._release_lease(lease, worker_token)
                    return GlobalFallbackCoordinatorResult(cancelled=True)

                if not self._heartbeat(lease, worker_token):
                    return GlobalFallbackCoordinatorResult(
                        failed=True,
                        error_code="LEASE_OWNERSHIP_LOST",
                        error_message="lost GLOBAL_BATCH lease before provider call",
                        outcome_severity=GlobalFallbackOutcomeSeverity.FAILED_TECHNICAL.value,
                    )

                durable = self.batch_journal.get_by_fingerprint(
                    job_id=job.id,
                    execution_id=exec_id,
                    batch_fingerprint=batch.fingerprint,
                )
                if durable is not None and durable.status is GlobalFallbackBatchStatus.COMPLETED:
                    ents = (durable.normalized_response_json or {}).get("entities") or []
                    plan = build_merge_plan(
                        batch_fingerprint=batch.fingerprint,
                        entities=ents if isinstance(ents, list) else [],
                        evidence_by_asset=evidence_by_asset,
                        ordered_asset_ids=batch.ordered_asset_ids,
                        frame_to_asset_map=durable.frame_to_asset_map,
                        filename_to_asset_id=name_map,
                    )
                    # Re-apply is idempotent via operation keys.
                    apply_res = self.merge_applier.apply(
                        job=job,
                        aisle=aisle,
                        asset_by_id=asset_by_id,
                        plan=plan,
                        batch_row=durable,
                        snapshot=snapshot,
                    )
                    result.applied_external += apply_res.applied
                    result.conflict_count += len(plan.conflicts)
                    result.unmapped_count += len(plan.unmapped)
                    result.kept_internal += len(plan.unchanged)
                    batch_summaries.append(self._batch_public(durable, reused=True))
                    self._emit(
                        job.id,
                        "fallback.batch_call_completed",
                        message="reused durable batch",
                        metadata={
                            "batch_index": batch.batch_index,
                            "batch_fingerprint": batch.fingerprint,
                            "reused": True,
                        },
                    )
                    continue

                batch_assets = [asset_by_id[aid] for aid in batch.ordered_asset_ids]
                now = self.clock.now()
                row = GlobalFallbackBatchRequest(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    execution_id=exec_id,
                    attempt=int(getattr(job, "attempt_count", 1) or 1),
                    batch_index=batch.batch_index,
                    batch_count=batch.batch_count,
                    batch_fingerprint=batch.fingerprint,
                    status=GlobalFallbackBatchStatus.PREPARED,
                    ordered_asset_ids=list(batch.ordered_asset_ids),
                    provider=str(getattr(snapshot, "provider", "") or ""),
                    model=getattr(snapshot, "model", None),
                    schema_version=GLOBAL_FALLBACK_SCHEMA_VERSION,
                    configuration_fingerprint=configuration_fingerprint,
                    prompt_fingerprint=pf,
                    prepared_image_hashes=[hashes[aid] for aid in batch.ordered_asset_ids],
                    created_at=now,
                    updated_at=now,
                    worker_token=worker_token,
                )
                inserted = self.batch_journal.try_insert(row)
                if inserted is None:
                    # Concurrent insert — reload
                    durable = self.batch_journal.get_by_fingerprint(
                        job_id=job.id,
                        execution_id=exec_id,
                        batch_fingerprint=batch.fingerprint,
                    )
                    if durable is None:
                        return GlobalFallbackCoordinatorResult(
                            failed=True,
                            error_code="BATCH_JOURNAL_CONFLICT",
                            error_message="could not claim batch fingerprint",
                            outcome_severity=GlobalFallbackOutcomeSeverity.FAILED_TECHNICAL.value,
                        )
                    row = durable
                else:
                    row = inserted

                if row.status is GlobalFallbackBatchStatus.COMPLETED and row.normalized_response_json:
                    # Another worker finished; reuse path above next iteration pattern
                    ents = (row.normalized_response_json or {}).get("entities") or []
                else:
                    row.status = GlobalFallbackBatchStatus.CALLING
                    row.updated_at = self.clock.now()
                    self.batch_journal.save(row)

                    self._emit(
                        job.id,
                        "fallback.batch_call_started",
                        message="GLOBAL_BATCH provider call started",
                        metadata={
                            "batch_index": batch.batch_index,
                            "batch_fingerprint": batch.fingerprint,
                            "asset_count": len(batch_assets),
                        },
                    )
                    analysis = self.batch_analyzer.analyze_batch(
                        job=job,
                        aisle=aisle,
                        assets=batch_assets,
                        batch=batch,
                        snapshot=snapshot,
                        prompt_fingerprint=pf,
                    )
                    result.requests_count += 1

                    if not analysis.ok:
                        row.status = GlobalFallbackBatchStatus.FAILED_RETRYABLE
                        row.error_code = analysis.error_code or "FALLBACK_BATCH_FAILED"
                        row.error_message = (analysis.error_message or "")[:500]
                        row.updated_at = self.clock.now()
                        self.batch_journal.save(row)
                        outcome = decide_global_fallback_outcome(
                            eligibility=eligibility,
                            provider_failed=True,
                            provider_error_code=row.error_code,
                            provider_error_message=row.error_message,
                        )
                        self._fail_or_complete_lease(lease, worker_token, failed=outcome.fail_job)
                        summary = self._build_summary(
                            mode=mode,
                            slices=slices,
                            batch_summaries=batch_summaries,
                            result=result,
                            snapshot=snapshot,
                            eligibility=eligibility,
                            outcome=outcome,
                            total_cost=total_cost,
                            total_prompt_tokens=total_prompt_tokens,
                            total_response_tokens=total_response_tokens,
                            total_duration=total_duration,
                            ordered_ids=tuple(a.id for a in eligible_assets),
                        )
                        self.persist_job_summary(job.id, summary)
                        return GlobalFallbackCoordinatorResult(
                            failed=outcome.fail_job,
                            error_code=outcome.error_code,
                            error_message=outcome.message,
                            outcome_severity=outcome.severity.value,
                            requests_count=result.requests_count,
                            batch_count=len(slices),
                            public_summary=summary,
                        )

                    report = analysis.raw_report or {
                        "schema_version": analysis.schema_version or GLOBAL_FALLBACK_SCHEMA_VERSION,
                        "entities": analysis.entities,
                        "total_entities_detected": len(analysis.entities),
                    }
                    try:
                        ents = validate_global_fallback_report(report)
                    except GlobalFallbackSchemaError as exc:
                        row.status = GlobalFallbackBatchStatus.FAILED_FINAL
                        row.error_code = exc.code
                        row.error_message = exc.message[:500]
                        row.updated_at = self.clock.now()
                        self.batch_journal.save(row)
                        outcome = decide_global_fallback_outcome(
                            eligibility=eligibility,
                            provider_failed=True,
                            provider_error_code=exc.code,
                            provider_error_message=exc.message,
                        )
                        self._fail_or_complete_lease(lease, worker_token, failed=outcome.fail_job)
                        summary = self._build_summary(
                            mode=mode,
                            slices=slices,
                            batch_summaries=batch_summaries,
                            result=result,
                            snapshot=snapshot,
                            eligibility=eligibility,
                            outcome=outcome,
                            total_cost=total_cost,
                            total_prompt_tokens=total_prompt_tokens,
                            total_response_tokens=total_response_tokens,
                            total_duration=total_duration,
                            ordered_ids=tuple(a.id for a in eligible_assets),
                        )
                        self.persist_job_summary(job.id, summary)
                        return GlobalFallbackCoordinatorResult(
                            failed=outcome.fail_job,
                            error_code=exc.code,
                            error_message=exc.message,
                            outcome_severity=outcome.severity.value,
                            requests_count=result.requests_count,
                            batch_count=len(slices),
                            public_summary=summary,
                        )

                    # Durable RESPONSE_RECEIVED before next batch / merge.
                    sanitized = sanitize_entities_for_storage(ents)
                    row.status = GlobalFallbackBatchStatus.RESPONSE_RECEIVED
                    row.normalized_response_json = {
                        "schema_version": GLOBAL_FALLBACK_SCHEMA_VERSION,
                        "entities": sanitized,
                        "total_entities_detected": len(sanitized),
                    }
                    row.response_sha256 = hashlib.sha256(
                        str(sanitized).encode("utf-8")
                    ).hexdigest()
                    row.frame_to_asset_map = dict(analysis.frame_to_asset_map or {})
                    row.estimated_cost = analysis.estimated_cost
                    row.prompt_tokens = analysis.prompt_tokens
                    row.response_tokens = analysis.response_tokens
                    row.duration_ms = analysis.duration_ms
                    if analysis.prompt_fingerprint:
                        row.prompt_fingerprint = analysis.prompt_fingerprint
                    row.updated_at = self.clock.now()
                    self.batch_journal.save(row)

                    row.status = GlobalFallbackBatchStatus.VALIDATED
                    row.updated_at = self.clock.now()
                    self.batch_journal.save(row)
                    ents = sanitized

                    if analysis.estimated_cost:
                        total_cost += float(analysis.estimated_cost)
                    if analysis.prompt_tokens:
                        total_prompt_tokens += int(analysis.prompt_tokens)
                    if analysis.response_tokens:
                        total_response_tokens += int(analysis.response_tokens)
                    if analysis.duration_ms:
                        total_duration += int(analysis.duration_ms)

                if not self._heartbeat(lease, worker_token):
                    return GlobalFallbackCoordinatorResult(
                        failed=True,
                        error_code="LEASE_OWNERSHIP_LOST",
                        error_message="lost lease before merge persist",
                        outcome_severity=GlobalFallbackOutcomeSeverity.FAILED_TECHNICAL.value,
                    )

                plan = build_merge_plan(
                    batch_fingerprint=batch.fingerprint,
                    entities=ents if isinstance(ents, list) else [],
                    evidence_by_asset=evidence_by_asset,
                    ordered_asset_ids=batch.ordered_asset_ids,
                    frame_to_asset_map=row.frame_to_asset_map,
                    filename_to_asset_id=name_map,
                )
                apply_res = self.merge_applier.apply(
                    job=job,
                    aisle=aisle,
                    asset_by_id=asset_by_id,
                    plan=plan,
                    batch_row=row,
                    snapshot=snapshot,
                )
                if apply_res.failed:
                    outcome = decide_global_fallback_outcome(
                        eligibility=eligibility,
                        persistence_inconsistent=True,
                        provider_error_message=apply_res.error_message,
                    )
                    self._fail_or_complete_lease(lease, worker_token, failed=True)
                    summary = self._build_summary(
                        mode=mode,
                        slices=slices,
                        batch_summaries=batch_summaries,
                        result=result,
                        snapshot=snapshot,
                        eligibility=eligibility,
                        outcome=outcome,
                        total_cost=total_cost,
                        total_prompt_tokens=total_prompt_tokens,
                        total_response_tokens=total_response_tokens,
                        total_duration=total_duration,
                        ordered_ids=tuple(a.id for a in eligible_assets),
                    )
                    self.persist_job_summary(job.id, summary)
                    return GlobalFallbackCoordinatorResult(
                        failed=True,
                        error_code=apply_res.error_code,
                        error_message=apply_res.error_message,
                        outcome_severity=outcome.severity.value,
                        requests_count=result.requests_count,
                        batch_count=len(slices),
                        public_summary=summary,
                    )

                result.applied_external += apply_res.applied
                result.conflict_count += len(plan.conflicts)
                result.unmapped_count += len(plan.unmapped)
                result.kept_internal += len(plan.unchanged)
                result.entity_count += len(ents) if isinstance(ents, list) else 0
                batch_summaries.append(self._batch_public(row, reused=False))

            outcome = decide_global_fallback_outcome(eligibility=eligibility)
            summary = self._build_summary(
                mode=mode,
                slices=slices,
                batch_summaries=batch_summaries,
                result=result,
                snapshot=snapshot,
                eligibility=eligibility,
                outcome=outcome,
                total_cost=total_cost,
                total_prompt_tokens=total_prompt_tokens,
                total_response_tokens=total_response_tokens,
                total_duration=total_duration,
                ordered_ids=tuple(
                    aid for s in slices for aid in s.ordered_asset_ids
                ),
            )
            # Persist durable summary BEFORE completing lease.
            self.persist_job_summary(job.id, summary)
            self._complete_lease(lease, worker_token)
            result.public_summary = summary
            result.outcome_severity = outcome.severity.value
            return result
        except Exception as exc:
            logger.exception("global_fallback.unhandled job_id=%s", job.id)
            self._fail_lease(lease, worker_token)
            return GlobalFallbackCoordinatorResult(
                failed=True,
                error_code="FALLBACK_BATCH_UNHANDLED",
                error_message=f"{type(exc).__name__}: {exc}"[:500],
                outcome_severity=GlobalFallbackOutcomeSeverity.FAILED_TECHNICAL.value,
            )

    def _build_summary(self, **kwargs: Any) -> dict[str, Any]:
        mode = kwargs["mode"]
        result: GlobalFallbackCoordinatorResult = kwargs["result"]
        snapshot = kwargs["snapshot"]
        eligibility = kwargs["eligibility"]
        outcome = kwargs["outcome"]
        return {
            "fallback_mode": mode,
            "needs_fallback": True,
            "execution_scope": GLOBAL_FALLBACK_EXECUTION_SCOPE,
            "schema_version": GLOBAL_FALLBACK_SCHEMA_VERSION,
            "analysis_contract": GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
            "provider": getattr(snapshot, "provider", None),
            "model": getattr(snapshot, "model", None),
            "prompt_key": GLOBAL_FALLBACK_PROMPT_KEY,
            "images_sent": len(kwargs["ordered_ids"]),
            "batch_count": len(kwargs["slices"]),
            "requests_count": result.requests_count,
            "batches_reused": sum(1 for b in kwargs["batch_summaries"] if b.get("reused")),
            "batches_completed": sum(
                1 for b in kwargs["batch_summaries"] if b.get("status") == "COMPLETED"
            ),
            "entity_count": result.entity_count,
            "conflicts": result.conflict_count,
            "unmapped": result.unmapped_count,
            "applied_external": result.applied_external,
            "kept_internal": result.kept_internal,
            "estimated_cost_total": kwargs["total_cost"] or None,
            "prompt_tokens": kwargs["total_prompt_tokens"] or None,
            "response_tokens": kwargs["total_response_tokens"] or None,
            "duration_ms": kwargs["total_duration"] or None,
            "eligibility_reason": eligibility.reason,
            "outcome_severity": outcome.severity.value,
            "batches": kwargs["batch_summaries"],
            "persistence_status": "COMPLETED"
            if not outcome.fail_job
            else "FAILED",
        }

    @staticmethod
    def _batch_public(row: GlobalFallbackBatchRequest, *, reused: bool) -> dict[str, Any]:
        return {
            "batch_index": row.batch_index,
            "batch_count": row.batch_count,
            "batch_fingerprint": row.batch_fingerprint,
            "status": row.status.value,
            "reused": reused,
            "entity_count": len((row.normalized_response_json or {}).get("entities") or []),
            "estimated_cost": row.estimated_cost,
            "prompt_tokens": row.prompt_tokens,
            "response_tokens": row.response_tokens,
            "duration_ms": row.duration_ms,
            "prompt_fingerprint": row.prompt_fingerprint,
        }

    @staticmethod
    def _default_prompt_fingerprint(snapshot: Any) -> str:
        sp = getattr(snapshot, "supplier_prompt", None)
        sha = None
        if isinstance(sp, dict):
            sha = sp.get("content_sha256")
        rules = getattr(snapshot, "client_rules", None)
        return prompt_fingerprint_from_parts(
            prompt_key=GLOBAL_FALLBACK_PROMPT_KEY,
            schema_version=GLOBAL_FALLBACK_SCHEMA_VERSION,
            composition_version="hybrid",
            base_prompt_sha256=None,
            supplier_content_sha256=str(sha) if sha else None,
            client_rules=rules if isinstance(rules, dict) else None,
        )

    def _acquire_lease(self, job_id: str, worker_token: str) -> JobProcessingLease | None:
        return self.lease_repo.try_acquire_lease(
            job_id=job_id,
            strategy=GLOBAL_FALLBACK_STRATEGY_KEY,
            execution_scope=ExecutionScope.AISLE_BATCH.value,
            worker_token=worker_token,
            now=self.clock.now(),
            lease_duration_seconds=self.lease_duration_seconds,
        )

    def _heartbeat(self, lease: JobProcessingLease, worker_token: str) -> bool:
        try:
            updated = self.lease_repo.heartbeat(
                lease.id,
                worker_token=worker_token,
                now=self.clock.now(),
                lease_duration_seconds=self.lease_duration_seconds,
            )
            return updated is not None
        except Exception:
            logger.warning("global_fallback.heartbeat_failed lease_id=%s", lease.id)
            return False

    def _complete_lease(self, lease: JobProcessingLease, worker_token: str) -> None:
        try:
            self.lease_repo.complete(lease.id, worker_token=worker_token, now=self.clock.now())
        except Exception:
            logger.warning("global_fallback.lease_complete_failed lease_id=%s", lease.id)

    def _fail_lease(self, lease: JobProcessingLease, worker_token: str) -> None:
        try:
            self.lease_repo.fail(lease.id, worker_token=worker_token, now=self.clock.now())
        except Exception:
            logger.warning("global_fallback.lease_fail_failed lease_id=%s", lease.id)

    def _release_lease(self, lease: JobProcessingLease, worker_token: str) -> None:
        try:
            self.lease_repo.release(lease.id, worker_token=worker_token, now=self.clock.now())
        except Exception:
            logger.warning("global_fallback.lease_release_failed lease_id=%s", lease.id)

    def _fail_or_complete_lease(
        self, lease: JobProcessingLease, worker_token: str, *, failed: bool
    ) -> None:
        if failed:
            self._fail_lease(lease, worker_token)
        else:
            self._complete_lease(lease, worker_token)

    def _emit(
        self,
        job_id: str,
        event_type: str,
        *,
        message: str | None = None,
        error_code: str | None = None,
        metadata: dict | None = None,
        severity: str = "INFO",
    ) -> None:
        if self.event_publisher is None:
            return
        try:
            self.event_publisher.publish(
                job_id=job_id,
                event_type=event_type,
                strategy=GLOBAL_FALLBACK_STRATEGY_KEY,
                severity=severity,
                message=message,
                error_code=error_code,
                metadata=metadata,
            )
        except Exception:
            logger.debug(
                "global_fallback.event_publish_skipped job_id=%s event=%s",
                job_id,
                event_type,
                exc_info=True,
            )
