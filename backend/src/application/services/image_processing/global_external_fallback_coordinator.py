"""Global EXTERNAL_FALLBACK_MODE=GLOBAL_BATCH coordinator (after internal aisle pass).

Runs once per job (or per deterministic ≤48 batch), never inside the per-asset loop.
Reuses hybrid GlobalEntityResponseV21 analysis via an injected batch analyzer.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

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
    GlobalFallbackBatchSlice,
    build_batch_slices,
    stable_ordered_asset_ids,
)
from src.application.services.image_processing.global_fallback_merge_policy import (
    ExternalEntityEvidence,
    GlobalFallbackMergeAction,
    GlobalFallbackMergeDecision,
    InternalAssetEvidence,
    decide_merge_for_asset,
    decide_unmapped_entity,
    normalize_provider_source_image_id,
)
from src.domain.assets.entities import SourceAsset
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.job_processing_lease import JobProcessingLease

logger = logging.getLogger(__name__)

EXTERNAL_PROVIDER_STRATEGY = "EXTERNAL_PROVIDER"


class GlobalFallbackBatchAnalyzer(Protocol):
    """Runs one hybrid GlobalEntityResponseV21 call for an ordered asset batch."""

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
    provider: str | None = None
    model: str | None = None
    estimated_cost: float | None = None
    prompt_tokens: int | None = None
    response_tokens: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_report: dict[str, Any] | None = None
    duration_ms: int | None = None


@dataclass
class GlobalFallbackCoordinatorResult:
    skipped: bool = False
    skip_reason: str | None = None
    cancelled: bool = False
    failed: bool = False
    error_code: str | None = None
    error_message: str | None = None
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
    """Orchestrates GLOBAL_BATCH after CODE_SCAN / INTERNAL_OCR aisle completion."""

    lease_repo: Any
    clock: Any
    batch_analyzer: GlobalFallbackBatchAnalyzer
    result_persister: Any
    event_publisher: Any | None = None
    state_repo: Any | None = None
    lease_duration_seconds: int = 600
    max_frames_per_batch: int = 48
    load_internal_evidence: Callable[[str, str], InternalAssetEvidence | None] | None = None
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
        configuration_fingerprint: str = "",
        prompt_fingerprint: str = "",
        execution_id: str | None = None,
    ) -> GlobalFallbackCoordinatorResult:
        """Entry point: only call after internal aisle pass finished and persisted."""
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
            )

        if is_cancelled():
            return GlobalFallbackCoordinatorResult(cancelled=True, skip_reason="cancelled")

        eligible = [a for a in assets if a is not None and getattr(a, "id", None)]
        if not eligible:
            self._emit(
                job.id,
                "fallback.batch_evaluated",
                message="no eligible assets for GLOBAL_BATCH",
                metadata={"asset_count": 0, "fallback_mode": mode},
            )
            return GlobalFallbackCoordinatorResult(
                skipped=True, skip_reason="no_eligible_assets"
            )

        # Supplier prompt mandatory when supplier associated.
        if getattr(snapshot, "supplier_prompt_required", False):
            sp = getattr(snapshot, "supplier_prompt", None)
            content = ""
            if isinstance(sp, dict):
                content = str(sp.get("content") or sp.get("instructions_text") or "")
            if not content.strip():
                self._emit(
                    job.id,
                    "fallback.batch_failed",
                    message="missing supplier instructions_text",
                    error_code="SUPPLIER_PROMPT_REQUIRED",
                    severity="ERROR",
                    metadata={"missing": "supplier_prompt.content"},
                )
                return GlobalFallbackCoordinatorResult(
                    failed=True,
                    error_code="SUPPLIER_PROMPT_REQUIRED",
                    error_message="supplier instructions_text required for GLOBAL_BATCH",
                )

        if not prompt_fingerprint:
            prompt_fingerprint = self._prompt_fingerprint_from_snapshot(snapshot)

        ordered_ids = stable_ordered_asset_ids([a.id for a in eligible])
        asset_by_id = {a.id: a for a in eligible}
        slices = build_batch_slices(
            ordered_ids,
            max_per_batch=int(self.max_frames_per_batch),
            job_id=job.id,
            execution_id=execution_id or job.id,
            attempt=int(getattr(job, "attempt_count", 1) or 1),
            fallback_mode=mode,
            provider=str(getattr(snapshot, "provider", "") or ""),
            model=getattr(snapshot, "model", None),
            schema_version=GLOBAL_FALLBACK_SCHEMA_VERSION,
            configuration_fingerprint=configuration_fingerprint,
            prompt_fingerprint=prompt_fingerprint,
        )

        self._emit(
            job.id,
            "fallback.batch_evaluated",
            message="GLOBAL_BATCH evaluated",
            metadata={
                "fallback_mode": mode,
                "execution_scope": GLOBAL_FALLBACK_EXECUTION_SCOPE,
                "schema_version": GLOBAL_FALLBACK_SCHEMA_VERSION,
                "analysis_contract": GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
                "asset_count": len(ordered_ids),
                "batch_count": len(slices),
                "ordered_asset_ids": list(ordered_ids),
                "provider": getattr(snapshot, "provider", None),
                "model": getattr(snapshot, "model", None),
            },
        )

        durable = self._load_durable_batches(job)
        if self._all_batches_durable(slices, durable):
            summary = self._public_summary_from_durable(
                job, slices, durable, snapshot, ordered_ids
            )
            return GlobalFallbackCoordinatorResult(
                skipped=True,
                skip_reason="durable_result_reused",
                requests_count=0,
                batch_count=len(slices),
                public_summary=summary,
            )

        lease = self._acquire_lease(job.id, worker_token)
        if lease is None:
            return GlobalFallbackCoordinatorResult(
                skipped=True, skip_reason="lease_not_acquired"
            )

        result = GlobalFallbackCoordinatorResult(batch_count=len(slices))
        all_entities: list[dict[str, Any]] = []
        batch_meta: list[dict[str, Any]] = []

        try:
            if is_cancelled():
                self._release_lease(lease, worker_token)
                return GlobalFallbackCoordinatorResult(cancelled=True)

            name_map: dict[str, str] = {}
            if self.filename_to_asset_id is not None:
                name_map = self.filename_to_asset_id(eligible)

            for batch in slices:
                if is_cancelled():
                    self._release_lease(lease, worker_token)
                    return GlobalFallbackCoordinatorResult(cancelled=True)

                prior = durable.get(batch.fingerprint)
                if isinstance(prior, dict) and prior.get("status") == "COMPLETED":
                    ents = prior.get("entities") or []
                    if isinstance(ents, list):
                        all_entities.extend(e for e in ents if isinstance(e, dict))
                    batch_meta.append(prior)
                    self._emit(
                        job.id,
                        "fallback.batch_call_completed",
                        message="reused durable batch result",
                        metadata={
                            "batch_index": batch.batch_index,
                            "batch_count": batch.batch_count,
                            "batch_fingerprint": batch.fingerprint,
                            "reused": True,
                            "entity_count": len(ents) if isinstance(ents, list) else 0,
                        },
                    )
                    continue

                batch_assets = [asset_by_id[aid] for aid in batch.ordered_asset_ids]
                self._emit(
                    job.id,
                    "fallback.batch_prepared",
                    message="GLOBAL_BATCH prepared",
                    metadata={
                        "batch_index": batch.batch_index,
                        "batch_count": batch.batch_count,
                        "asset_count": len(batch_assets),
                        "ordered_asset_ids": list(batch.ordered_asset_ids),
                        "batch_fingerprint": batch.fingerprint,
                    },
                )
                self._emit(
                    job.id,
                    "fallback.prompt_resolved",
                    message="GLOBAL_BATCH prompt resolved",
                    metadata={
                        "prompt_key": GLOBAL_FALLBACK_PROMPT_KEY,
                        "schema_version": GLOBAL_FALLBACK_SCHEMA_VERSION,
                        "analysis_contract": GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
                        "prompt_fingerprint": prompt_fingerprint,
                        "supplier_prompt_id": (
                            (snapshot.supplier_prompt or {}).get("prompt_id")
                            if isinstance(getattr(snapshot, "supplier_prompt", None), dict)
                            else None
                        ),
                    },
                )
                self._emit(
                    job.id,
                    "fallback.batch_call_started",
                    message="GLOBAL_BATCH provider call started",
                    metadata={
                        "batch_index": batch.batch_index,
                        "batch_count": batch.batch_count,
                        "batch_fingerprint": batch.fingerprint,
                        "provider": getattr(snapshot, "provider", None),
                        "model": getattr(snapshot, "model", None),
                        "schema": GLOBAL_FALLBACK_SCHEMA_VERSION,
                    },
                )

                analysis = self.batch_analyzer.analyze_batch(
                    job=job,
                    aisle=aisle,
                    assets=batch_assets,
                    batch=batch,
                    snapshot=snapshot,
                    prompt_fingerprint=prompt_fingerprint,
                )
                result.requests_count += 1 if analysis.ok or analysis.error_code else 1

                if not analysis.ok:
                    self._emit(
                        job.id,
                        "fallback.batch_failed",
                        message=analysis.error_message or "batch failed",
                        error_code=analysis.error_code or "FALLBACK_BATCH_FAILED",
                        severity="ERROR",
                        metadata={
                            "batch_index": batch.batch_index,
                            "batch_fingerprint": batch.fingerprint,
                        },
                    )
                    self._fail_lease(lease, worker_token)
                    result.failed = True
                    result.error_code = analysis.error_code or "FALLBACK_BATCH_FAILED"
                    result.error_message = analysis.error_message
                    return result

                # Reject accidental single-label / external_fallback_v1 contract.
                schema = str(analysis.schema_version or "").strip()
                if schema and schema not in (
                    GLOBAL_FALLBACK_SCHEMA_VERSION,
                    "2.1",
                    "v21",
                ):
                    if "external_fallback" in schema.lower():
                        self._fail_lease(lease, worker_token)
                        result.failed = True
                        result.error_code = "EXTERNAL_SCHEMA_CONTRACT_MISMATCH"
                        result.error_message = (
                            f"GLOBAL_BATCH requires GlobalEntityResponseV21; got {schema}"
                        )
                        return result

                ents = list(analysis.entities or [])
                all_entities.extend(ents)
                meta = {
                    "status": "COMPLETED",
                    "batch_index": batch.batch_index,
                    "batch_count": batch.batch_count,
                    "batch_fingerprint": batch.fingerprint,
                    "ordered_asset_ids": list(batch.ordered_asset_ids),
                    "entity_count": len(ents),
                    "provider": analysis.provider or getattr(snapshot, "provider", None),
                    "model": analysis.model or getattr(snapshot, "model", None),
                    "schema_version": analysis.schema_version
                    or GLOBAL_FALLBACK_SCHEMA_VERSION,
                    "prompt_key": analysis.prompt_key or GLOBAL_FALLBACK_PROMPT_KEY,
                    "prompt_fingerprint": analysis.prompt_fingerprint or prompt_fingerprint,
                    "estimated_cost": analysis.estimated_cost,
                    "prompt_tokens": analysis.prompt_tokens,
                    "response_tokens": analysis.response_tokens,
                    "duration_ms": analysis.duration_ms,
                    "entities": ents,
                }
                batch_meta.append(meta)
                durable[batch.fingerprint] = meta
                self._emit(
                    job.id,
                    "fallback.batch_call_completed",
                    message="GLOBAL_BATCH provider call completed",
                    metadata={
                        "batch_index": batch.batch_index,
                        "batch_count": batch.batch_count,
                        "batch_fingerprint": batch.fingerprint,
                        "entity_count": len(ents),
                        "estimated_cost": analysis.estimated_cost,
                        "duration_ms": analysis.duration_ms,
                    },
                )
                self._emit(
                    job.id,
                    "fallback.batch_validation_completed",
                    message="GLOBAL_BATCH response validated",
                    metadata={
                        "schema_version": meta["schema_version"],
                        "analysis_contract": GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
                        "entity_count": len(ents),
                    },
                )

            self._emit(
                job.id,
                "fallback.batch_merge_started",
                message="GLOBAL_BATCH merge started",
                metadata={"entity_count": len(all_entities)},
            )
            decisions = self._merge_entities(
                job=job,
                aisle=aisle,
                asset_by_id=asset_by_id,
                entities=all_entities,
                name_map=name_map,
                snapshot=snapshot,
            )
            result.decisions = decisions
            for d in decisions:
                if d.action is GlobalFallbackMergeAction.KEEP_INTERNAL:
                    result.kept_internal += 1
                elif d.action in (
                    GlobalFallbackMergeAction.APPLY_EXTERNAL,
                    GlobalFallbackMergeAction.COMBINE_QUANTITY,
                ):
                    result.applied_external += 1
                elif d.action is GlobalFallbackMergeAction.CONFLICT_REVIEW:
                    result.conflict_count += 1
                elif d.action is GlobalFallbackMergeAction.UNMAPPED_REVIEW:
                    result.unmapped_count += 1
            result.entity_count = len(all_entities)
            self._emit(
                job.id,
                "fallback.batch_merge_completed",
                message="GLOBAL_BATCH merge completed",
                metadata={
                    "applied_external": result.applied_external,
                    "kept_internal": result.kept_internal,
                    "conflicts": result.conflict_count,
                    "unmapped": result.unmapped_count,
                },
            )

            self._emit(
                job.id,
                "fallback.batch_persistence_started",
                message="GLOBAL_BATCH persistence started",
                metadata={"apply_count": result.applied_external},
            )
            # Persistence of APPLY/COMBINE happens inside _merge_entities via persister.
            self._complete_lease(lease, worker_token)
            self._emit(
                job.id,
                "fallback.batch_persistence_completed",
                message="GLOBAL_BATCH persistence completed",
                metadata={"apply_count": result.applied_external},
            )

            result.public_summary = {
                "fallback_mode": mode,
                "execution_scope": GLOBAL_FALLBACK_EXECUTION_SCOPE,
                "schema_version": GLOBAL_FALLBACK_SCHEMA_VERSION,
                "analysis_contract": GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
                "provider": getattr(snapshot, "provider", None),
                "model": getattr(snapshot, "model", None),
                "prompt_key": GLOBAL_FALLBACK_PROMPT_KEY,
                "images_sent": len(ordered_ids),
                "ordered_asset_ids": list(ordered_ids),
                "batch_count": len(slices),
                "requests_count": result.requests_count,
                "entity_count": result.entity_count,
                "conflicts": result.conflict_count,
                "unmapped": result.unmapped_count,
                "applied_external": result.applied_external,
                "kept_internal": result.kept_internal,
                "batches": [
                    {k: v for k, v in b.items() if k != "entities"} for b in batch_meta
                ],
                "durable_batches": durable,
                "persistence_status": "COMPLETED",
            }
            return result
        except Exception as exc:
            logger.exception("global_fallback.unhandled job_id=%s", job.id)
            self._fail_lease(lease, worker_token)
            self._emit(
                job.id,
                "fallback.batch_failed",
                message=type(exc).__name__,
                error_code="FALLBACK_BATCH_UNHANDLED",
                severity="ERROR",
            )
            return GlobalFallbackCoordinatorResult(
                failed=True,
                error_code="FALLBACK_BATCH_UNHANDLED",
                error_message=str(exc)[:500],
            )

    def _merge_entities(
        self,
        *,
        job: Any,
        aisle: Any,
        asset_by_id: dict[str, SourceAsset],
        entities: list[dict[str, Any]],
        name_map: dict[str, str],
        snapshot: Any,
    ) -> list[GlobalFallbackMergeDecision]:
        asset_ids = set(asset_by_id.keys())
        # First entity per asset wins for apply; conflicts still recorded.
        assigned: dict[str, dict[str, Any]] = {}
        decisions: list[GlobalFallbackMergeDecision] = []

        for ent in entities:
            if not isinstance(ent, dict):
                continue
            raw_src = ent.get("source_image_id") or ent.get("source_asset_id")
            mapped = normalize_provider_source_image_id(
                str(raw_src) if raw_src is not None else None,
                asset_id_set=asset_ids,
                filename_to_asset_id=name_map,
            )
            ext = ExternalEntityEvidence(
                internal_code=(
                    str(ent.get("internal_code")).strip()
                    if ent.get("internal_code") is not None
                    else None
                ),
                quantity=_coerce_qty(ent.get("quantity")),
                confidence=_coerce_float(ent.get("confidence")),
                source_image_id=mapped,
                raw=ent,
            )
            if mapped is None:
                decisions.append(decide_unmapped_entity(ext))
                continue
            if mapped in assigned:
                # Same label / duplicate entity for asset — keep first (historical dedupe).
                decisions.append(
                    GlobalFallbackMergeDecision(
                        action=GlobalFallbackMergeAction.KEEP_INTERNAL,
                        asset_id=mapped,
                        reason="duplicate_external_entity_deduped",
                        external=ext,
                    )
                )
                continue
            assigned[mapped] = ent

            internal = None
            if self.load_internal_evidence is not None:
                internal = self.load_internal_evidence(job.id, mapped)
            if internal is None:
                internal = InternalAssetEvidence(
                    asset_id=mapped,
                    status=None,
                    internal_code=None,
                    quantity=None,
                    resolved_internal=False,
                )
            decision = decide_merge_for_asset(internal=internal, external=ext)
            decisions.append(decision)

            if decision.action in (
                GlobalFallbackMergeAction.APPLY_EXTERNAL,
                GlobalFallbackMergeAction.COMBINE_QUANTITY,
            ):
                self._persist_external(
                    job=job,
                    aisle=aisle,
                    asset=asset_by_id[mapped],
                    external=ext,
                    snapshot=snapshot,
                    reason=decision.reason,
                )
            elif decision.action is GlobalFallbackMergeAction.CONFLICT_REVIEW:
                self._mark_conflict_review(
                    job=job,
                    asset_id=mapped,
                    decision=decision,
                )

        # Assets with no external entity: keep internal (explicit decision for observability).
        for aid in asset_ids:
            if aid in assigned:
                continue
            internal = None
            if self.load_internal_evidence is not None:
                internal = self.load_internal_evidence(job.id, aid)
            decisions.append(
                decide_merge_for_asset(internal=internal, external=None)
            )
        return decisions

    def _persist_external(
        self,
        *,
        job: Any,
        aisle: Any,
        asset: SourceAsset,
        external: ExternalEntityEvidence,
        snapshot: Any,
        reason: str,
    ) -> None:
        result = ImageProcessingResult(
            job_id=job.id,
            asset_id=asset.id,
            status=ImageResultStatus.RESOLVED_EXTERNAL,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            internal_code=external.internal_code,
            quantity=external.quantity,
            normalized_result={
                "internal_code": external.internal_code,
                "quantity": external.quantity,
                "confidence": external.confidence,
                "source_image_id": external.source_image_id,
            },
            additional_fields={
                "fallback_mode": EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH,
                "fallback_reason": reason,
                "execution_scope": ExecutionScope.AISLE_BATCH.value,
                "external_provider": getattr(snapshot, "provider", None),
                "external_model": getattr(snapshot, "model", None),
                "analysis_contract": GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
                "schema_version": GLOBAL_FALLBACK_SCHEMA_VERSION,
            },
            evidence={
                "provider": getattr(snapshot, "provider", None),
                "model": getattr(snapshot, "model", None),
                "raw_entity": external.raw,
            },
            provider_name=getattr(snapshot, "provider", None),
            model_name=getattr(snapshot, "model", None),
            execution_scope=ExecutionScope.AISLE_BATCH,
            logical_asset_attempt=True,
        )
        try:
            self.result_persister.persist(
                result=result,
                inventory_id=aisle.inventory_id,
                aisle_id=aisle.id,
            )
        except Exception:
            logger.exception(
                "global_fallback.persist_failed job_id=%s asset_id=%s",
                job.id,
                asset.id,
            )
            raise

        if self.state_repo is not None:
            try:
                state = self.state_repo.get_by_job_and_asset(job.id, asset.id)
                if state is not None:
                    from src.domain.image_processing.job_asset_processing_state import (
                        JobAssetProcessingStatus,
                    )

                    state.status = JobAssetProcessingStatus.RESOLVED
                    state.last_strategy = EXTERNAL_PROVIDER_STRATEGY
                    state.updated_at = self.clock.now()
                    self.state_repo.save(state)
            except Exception:
                logger.warning(
                    "global_fallback.state_update_failed job_id=%s asset_id=%s",
                    job.id,
                    asset.id,
                    exc_info=True,
                )

    def _mark_conflict_review(
        self,
        *,
        job: Any,
        asset_id: str,
        decision: GlobalFallbackMergeDecision,
    ) -> None:
        if self.state_repo is None:
            return
        try:
            from src.domain.image_processing.job_asset_processing_state import (
                JobAssetProcessingStatus,
            )

            state = self.state_repo.get_by_job_and_asset(job.id, asset_id)
            if state is None:
                return
            # Do not overwrite a durable RESOLVED internal with silent failure.
            if state.status.value == "RESOLVED":
                state.error_code = "GLOBAL_FALLBACK_CONFLICT"
                state.error_message = decision.reason
            else:
                state.status = JobAssetProcessingStatus.PENDING_MANUAL_REVIEW
                state.error_code = "GLOBAL_FALLBACK_CONFLICT"
                state.error_message = decision.reason
            state.updated_at = self.clock.now()
            self.state_repo.save(state)
        except Exception:
            logger.warning(
                "global_fallback.conflict_mark_failed job_id=%s asset_id=%s",
                job.id,
                asset_id,
                exc_info=True,
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

    def _load_durable_batches(self, job: Any) -> dict[str, Any]:
        result_json = getattr(job, "result_json", None) or {}
        if not isinstance(result_json, dict):
            return {}
        block = result_json.get("global_fallback")
        if not isinstance(block, dict):
            return {}
        durable = block.get("durable_batches")
        return dict(durable) if isinstance(durable, dict) else {}

    def _all_batches_durable(
        self,
        slices: list[GlobalFallbackBatchSlice],
        durable: dict[str, Any],
    ) -> bool:
        if not slices:
            return False
        for batch in slices:
            meta = durable.get(batch.fingerprint)
            if not isinstance(meta, dict) or meta.get("status") != "COMPLETED":
                return False
        return True

    def _public_summary_from_durable(
        self,
        job: Any,
        slices: list[GlobalFallbackBatchSlice],
        durable: dict[str, Any],
        snapshot: Any,
        ordered_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        result_json = getattr(job, "result_json", None) or {}
        existing = {}
        if isinstance(result_json, dict):
            gf = result_json.get("global_fallback")
            if isinstance(gf, dict):
                existing = gf
        return {
            **existing,
            "fallback_mode": EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH,
            "reused_durable": True,
            "batch_count": len(slices),
            "requests_count": 0,
            "images_sent": len(ordered_ids),
            "provider": getattr(snapshot, "provider", None),
            "model": getattr(snapshot, "model", None),
            "schema_version": GLOBAL_FALLBACK_SCHEMA_VERSION,
            "analysis_contract": GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
            "persistence_status": "REUSED",
        }

    @staticmethod
    def _prompt_fingerprint_from_snapshot(snapshot: Any) -> str:
        parts = [
            GLOBAL_FALLBACK_PROMPT_KEY,
            GLOBAL_FALLBACK_SCHEMA_VERSION,
            str(getattr(snapshot, "provider", "") or ""),
            str(getattr(snapshot, "model", "") or ""),
        ]
        sp = getattr(snapshot, "supplier_prompt", None)
        if isinstance(sp, dict):
            parts.append(str(sp.get("content_sha256") or ""))
            parts.append(str(sp.get("prompt_id") or ""))
            parts.append(str(sp.get("prompt_version") or ""))
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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


def _coerce_qty(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    return _coerce_qty(value)
