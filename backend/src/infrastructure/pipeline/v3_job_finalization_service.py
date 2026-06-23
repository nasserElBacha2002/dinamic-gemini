"""
V3 successful job finalization — Phase 6 extraction from :class:`V3JobExecutor`.

Persists domain results, traceability artifacts, durable worker artifacts (or outbox),
and finalizes job/aisle success after a successful pipeline run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.artifact_publication_outbox_store import ArtifactPublicationOutboxStore
from src.application.ports.clock import Clock
from src.application.ports.repositories import JobRepository
from src.application.services.artifact_publication_dispatcher import (
    ArtifactPublicationDispatcher,
    ArtifactSourceStagingFailedError,
)
from src.application.services.traceability_artifact_service import TraceabilityArtifactService
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.domain.aisle.entities import Aisle
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_TRACEABILITY_MANIFEST,
    is_required_artifact_kind,
)
from src.domain.jobs.entities import Job
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationErrorCode,
    LastCompletedFinalizationStep,
)
from src.domain.traceability_artifact.errors import TraceabilityArtifactError
from src.infrastructure.pipeline.finalization_errors import (
    ArtifactPublishError,
    ArtifactPublishPartialError,
    ArtifactStoreUnavailableError,
)
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.v3_execution_artifacts_service import V3ExecutionArtifactsService
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_COMPOSITION
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.execution_log import ExecutionLogWriter
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult

logger = logging.getLogger(__name__)

RUN_ID = DEFAULT_V3_WORKER_RUN_SEGMENT


def _prompt_composition_from_run_metadata(run_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(run_metadata, dict):
        return None
    comp = run_metadata.get(LLM_METADATA_KEY_PROMPT_COMPOSITION)
    if isinstance(comp, dict):
        return comp
    legacy = run_metadata.get("prompt_composition")
    return legacy if isinstance(legacy, dict) else None


@dataclass(frozen=True)
class V3JobFinalizationRequest:
    """Persist + durable artifacts + mark_success after successful pipeline run."""

    job_id: str
    aisle: Aisle
    aisle_id: str
    run_dir: Path
    exec_log: ExecutionLogWriter
    pipeline_result: PipelineRunResult
    report_path: Path
    report: dict[str, Any]
    job: Job
    cancellation_checkpoint: Callable[[str, str | None, str], None]
    cancel_event_emitted: dict[str, bool]
    input_type: str | None = None
    canonical_traceability_expected: bool = False


class V3JobFinalizationService:
    """Owns successful finalization after a successful pipeline run."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        clock: Clock,
        state_service: V3JobExecutionStateService,
        persist_use_case: PersistAisleResultUseCase,
        artifacts_service: V3ExecutionArtifactsService,
        traceability_artifact_service: TraceabilityArtifactService,
        artifact_dispatcher: ArtifactPublicationDispatcher | None,
        artifact_manifest_store: ArtifactManifestStore | None,
        artifact_outbox_store: ArtifactPublicationOutboxStore | None,
        stage_recorder: FinalizationStageRecorder | None,
    ) -> None:
        self._job_repo = job_repo
        self._clock = clock
        self._state = state_service
        self._persist_use_case = persist_use_case
        self._artifacts = artifacts_service
        self._traceability_artifact_service = traceability_artifact_service
        self._artifact_dispatcher = artifact_dispatcher
        self._artifact_manifest_store = artifact_manifest_store
        self._artifact_outbox_store = artifact_outbox_store
        self._stage_recorder = stage_recorder

    def finalize_success(self, req: V3JobFinalizationRequest) -> bool:
        """Persist domain, upload durables, finalize success. True => caller must return True (failure)."""
        tracker = JobFinalizationTracker(
            job_repo=self._job_repo,
            clock=self._clock,
            job_id=req.job_id,
            stage_recorder=self._stage_recorder,
        )
        tracker.begin()
        try:
            return self._finalize_success_body(req, tracker)
        except PipelineCancellationRequestedError as cancel_exc:
            if tracker.last_completed == LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED:
                self._state.cancel_finalization_after_domain_commit(
                    req.job_id,
                    req.aisle,
                    str(cancel_exc),
                    tracker=tracker,
                    exec_log=req.exec_log,
                    cancel_event_emitted=req.cancel_event_emitted,
                )
            else:
                self._state.cancel_job_and_aisle(
                    req.job_id,
                    req.aisle,
                    str(cancel_exc),
                    exec_log=req.exec_log,
                    cancel_event_emitted=req.cancel_event_emitted,
                    tracker=tracker,
                )
            return True

    def _finalize_success_body(
        self,
        req: V3JobFinalizationRequest,
        tracker: JobFinalizationTracker,
    ) -> bool:
        req.exec_log.info("Persist", "Persist started", payload={"aisle_id": req.aisle_id})
        try:
            req.cancellation_checkpoint(
                "Persist",
                "pre_persist",
                "Job canceled before persistence",
            )
            self._persist_use_case.execute(
                PersistAisleResultCommand(
                    aisle_id=req.aisle_id,
                    job_id=req.job_id,
                    report=req.report,
                    run_dir=req.run_dir,
                    run_id=RUN_ID,
                    provider=(req.job.provider_name or "").strip() or None,
                    model_name=(req.job.model_name or "").strip() or None,
                    prompt_composition=_prompt_composition_from_run_metadata(req.pipeline_result.run_metadata),
                )
            )
        except PipelineCancellationRequestedError:
            raise
        except Exception as persist_e:
            req.exec_log.error(
                "Persist",
                f"Persist failed: {persist_e}",
                payload={"error": str(persist_e)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.DOMAIN_PERSISTENCE_FAILED,
                current_step=CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS,
                message=f"Persist: {persist_e}",
                metadata={"exception_type": type(persist_e).__name__},
            )
            return True

        try:
            # Post-UoW marker — see JobFinalizationTracker docstring for crash-window note.
            tracker.record_domain_persisted()
            req.exec_log.info("Persist", "Persist completed")
        except Exception as marker_e:
            req.exec_log.error(
                "Persist",
                f"Domain marker write failed: {marker_e}",
                payload={"error": str(marker_e)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                current_step=CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS,
                message=f"Domain marker write failed: {marker_e}",
                metadata={
                    "domain_commit_completed": True,
                    "marker_write_completed": False,
                    "verification_required": True,
                    "failed_marker": "DOMAIN_RESULTS_PERSISTED",
                    "exception_type": type(marker_e).__name__,
                },
            )
            return True

        logger.info(
            "v3_job_domain_persist_complete job_id=%s aisle_id=%s next_step=traceability_artifact_generation",
            req.job_id,
            req.aisle_id,
        )

        prompt_composition = _prompt_composition_from_run_metadata(req.pipeline_result.run_metadata)
        required_kind_overrides: dict[str, bool] = {}
        traceability_required = self._traceability_artifact_service.is_required_for_run(
            input_type=req.input_type,
            canonical_traceability_expected=req.canonical_traceability_expected,
            prompt_composition=prompt_composition,
        )
        try:
            if traceability_required:
                self._traceability_artifact_service.generate_and_write(
                    job_id=req.job_id,
                    inventory_id=req.aisle.inventory_id,
                    aisle_id=req.aisle_id,
                    run_id=RUN_ID,
                    run_dir=req.run_dir,
                    provider=(req.job.provider_name or "").strip() or None,
                    model_name=(req.job.model_name or "").strip() or None,
                    prompt_composition=prompt_composition,
                    run_metadata=req.pipeline_result.run_metadata,
                    hybrid_report=req.report,
                    input_type=req.input_type,
                    canonical_traceability_expected=req.canonical_traceability_expected,
                )
                required_kind_overrides[ARTIFACT_KIND_TRACEABILITY_MANIFEST] = True
        except TraceabilityArtifactError as trace_exc:
            req.exec_log.error(
                "Artifacts",
                f"Traceability artifact generation failed: {trace_exc}",
                payload={
                    "error": str(trace_exc)[:500],
                    "traceability_error_code": trace_exc.error_code,
                },
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_SOURCE_STAGING_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Traceability artifact generation failed: {trace_exc}",
                metadata={
                    "artifact_kind": ARTIFACT_KIND_TRACEABILITY_MANIFEST,
                    "traceability_error_code": trace_exc.error_code,
                    "domain_commit_completed": True,
                },
            )
            return True
        except Exception as trace_exc:
            req.exec_log.error(
                "Artifacts",
                f"Traceability artifact generation failed: {trace_exc}",
                payload={"error": str(trace_exc)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_SOURCE_STAGING_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Traceability artifact generation failed: {trace_exc}",
                metadata={
                    "artifact_kind": ARTIFACT_KIND_TRACEABILITY_MANIFEST,
                    "exception_type": type(trace_exc).__name__,
                    "domain_commit_completed": True,
                },
            )
            return True

        logger.info(
            "v3_job_traceability_artifact_ready job_id=%s aisle_id=%s next_step=durable_artifact_upload",
            req.job_id,
            req.aisle_id,
        )

        try:
            self._artifacts.require_store()
        except ArtifactStoreUnavailableError as store_err:
            msg = str(store_err)
            logger.error("v3_job_id=%s %s", req.job_id, msg)
            req.exec_log.error("Artifacts", msg)
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_STORE_UNAVAILABLE,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=msg,
            )
            return True

        durable_meta: dict[str, dict[str, Any]] | None = None
        try:
            req.cancellation_checkpoint(
                "Artifacts",
                "pre_upload",
                "Job canceled before artifact upload",
            )
            if (
                required_kind_overrides.get(ARTIFACT_KIND_TRACEABILITY_MANIFEST)
                and self._artifact_dispatcher is None
            ):
                msg = (
                    "Traceability manifest publication requires artifact outbox; "
                    "legacy non-outbox durable upload path is unsupported for required "
                    "traceability artifacts"
                )
                logger.error("v3_job_id=%s %s", req.job_id, msg)
                req.exec_log.error(
                    "Artifacts",
                    msg,
                    payload={
                        "artifact_kind": ARTIFACT_KIND_TRACEABILITY_MANIFEST,
                        "traceability_error_code": "ARTIFACT_OUTBOX_REQUIRED_FOR_TRACEABILITY",
                    },
                )
                self._state.fail_finalization_and_aisle(
                    req.job_id,
                    req.aisle,
                    tracker=tracker,
                    error_code=FinalizationErrorCode.ARTIFACT_SOURCE_STAGING_FAILED,
                    current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                    message=msg,
                    metadata={
                        "artifact_kind": ARTIFACT_KIND_TRACEABILITY_MANIFEST,
                        "traceability_error_code": "ARTIFACT_OUTBOX_REQUIRED_FOR_TRACEABILITY",
                        "domain_commit_completed": True,
                    },
                )
                return True
            if self._artifact_dispatcher is not None:
                return self.publish_artifacts_via_outbox(
                    req, tracker, required_kind_overrides=required_kind_overrides
                )
            durable_meta = self._artifacts.publish_worker_durables(
                job_id=req.job_id,
                run_segment=RUN_ID,
                run_dir=req.run_dir,
            )
            logger.info(
                "worker_durable_artifacts_ready_for_job_metadata job_id=%s kinds=%s",
                req.job_id,
                sorted(durable_meta.keys()),
            )
        except PipelineCancellationRequestedError:
            raise
        except ArtifactPublishPartialError as partial_exc:
            logger.exception(
                "worker_durable_artifact_publish_partial job_id=%s failed_kind=%s",
                req.job_id,
                partial_exc.failed_kind,
            )
            req.exec_log.error(
                "Artifacts",
                f"Partial durable artifact upload: {partial_exc}",
                payload={"error": str(partial_exc)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Durable artifact upload partial failure: {partial_exc}",
                metadata={
                    "failed_kind": partial_exc.failed_kind,
                    "published_artifacts": partial_exc.published,
                },
            )
            return True
        except (ArtifactPublishError, FileNotFoundError) as artifact_exc:
            logger.exception(
                "worker_durable_artifact_upload_failed job_id=%s",
                req.job_id,
            )
            req.exec_log.error(
                "Artifacts",
                f"Durable artifact upload failed: {artifact_exc}",
                payload={"error": str(artifact_exc)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Durable artifact upload failed: {artifact_exc}",
            )
            return True
        except Exception as artifact_exc:
            logger.exception(
                "worker_durable_artifact_publish_unexpected job_id=%s",
                req.job_id,
            )
            req.exec_log.error(
                "Artifacts",
                f"Durable artifact upload failed: {artifact_exc}",
                payload={"error": str(artifact_exc)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Durable artifact upload failed: {artifact_exc}",
                metadata={"exception_type": type(artifact_exc).__name__},
            )
            return True

        assert durable_meta is not None
        try:
            tracker.record_artifacts_published(durable_artifacts=durable_meta)
        except Exception as marker_e:
            req.exec_log.error(
                "Artifacts",
                f"Artifact marker write failed: {marker_e}",
                payload={"error": str(marker_e)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Artifact marker write failed: {marker_e}",
                metadata={
                    "artifact_upload_completed": True,
                    "marker_write_completed": False,
                    "verification_required": True,
                    "failed_marker": "ARTIFACTS_PUBLISHED",
                    "published_artifact_kinds": sorted(durable_meta.keys()),
                    "exception_type": type(marker_e).__name__,
                },
            )
            return True

        try:
            self._state.finalize_success(
                req.job_id,
                req.aisle,
                req.report_path,
                tracker=tracker,
                run_metadata=req.pipeline_result.run_metadata,
                durable_artifacts=durable_meta,
            )
        except Exception:
            logger.exception("v3_job_finalization_terminal_failed job_id=%s", req.job_id)
            return True

        logger.info(
            "v3 mark success: job_id=%s inventory_id=%s aisle_id=%s report_path=%s",
            req.job_id,
            req.aisle.inventory_id,
            req.aisle_id,
            str(req.report_path),
        )
        return False

    def publish_artifacts_via_outbox(
        self,
        req: V3JobFinalizationRequest,
        tracker: JobFinalizationTracker,
        *,
        required_kind_overrides: dict[str, bool] | None = None,
    ) -> bool:
        assert self._artifact_dispatcher is not None
        try:
            self._artifact_dispatcher.register_publication_work(
                job_id=req.job_id,
                run_segment=RUN_ID,
                run_dir=req.run_dir,
                required_kind_overrides=required_kind_overrides,
            )
        except ArtifactSourceStagingFailedError as exc:
            staging_code = getattr(exc, "error_code", "ARTIFACT_STAGING_FAILED")
            req.exec_log.error(
                "Artifacts",
                f"Required artifact staging failed: {exc}",
                payload={
                    "error": str(exc)[:500],
                    "staging_error_code": staging_code,
                },
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_SOURCE_STAGING_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Required artifact staging failed: {exc}",
                metadata={
                    "verification_required": True,
                    "staging_error_code": staging_code,
                },
            )
            return True
        try:
            dispatch_result = self._artifact_dispatcher.dispatch_job(
                job_id=req.job_id,
                run_segment=RUN_ID,
                run_dir=req.run_dir,
                tracker=tracker,
                continuation_aisle=req.aisle,
                report_path=req.report_path,
                run_metadata=req.pipeline_result.run_metadata,
            )
        except Exception as exc:
            job = self._job_repo.get_by_id(req.job_id)
            if job is not None and job.finalization_error_code:
                return True
            manifest = self._artifact_manifest_store
            if manifest is not None and manifest.required_kinds_published(req.job_id):
                published_kinds = sorted(
                    entry.artifact_kind
                    for entry in manifest.list_entries(req.job_id)
                    if entry.status == ArtifactManifestStatus.PUBLISHED
                )
                req.exec_log.error(
                    "Artifacts",
                    f"Artifact marker write failed: {exc}",
                    payload={"error": str(exc)[:500]},
                )
                self._state.fail_finalization_and_aisle(
                    req.job_id,
                    req.aisle,
                    tracker=tracker,
                    error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                    current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                    message=f"Artifact marker write failed: {exc}",
                    metadata={
                        "artifact_upload_completed": True,
                        "marker_write_completed": False,
                        "verification_required": True,
                        "failed_marker": "ARTIFACTS_PUBLISHED",
                        "published_artifact_kinds": published_kinds,
                        "exception_type": type(exc).__name__,
                    },
                )
                return True
            req.exec_log.error(
                "Artifacts",
                f"Artifact publication dispatch failed: {exc}",
                payload={"error": str(exc)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Artifact publication dispatch failed: {exc}",
                metadata={
                    "artifact_upload_completed": False,
                    "marker_write_completed": False,
                    "verification_required": True,
                    "exception_type": type(exc).__name__,
                },
            )
            return True
        if dispatch_result.continuation_started:
            logger.info(
                "v3 mark success via outbox: job_id=%s inventory_id=%s aisle_id=%s",
                req.job_id,
                req.aisle.inventory_id,
                req.aisle_id,
            )
            return False
        if dispatch_result.required_complete:
            try:
                tracker.record_artifacts_published(durable_artifacts=dispatch_result.durable_meta)
            except Exception as marker_e:
                req.exec_log.error(
                    "Artifacts",
                    f"Artifact marker write failed: {marker_e}",
                    payload={"error": str(marker_e)[:500]},
                )
                self._state.fail_finalization_and_aisle(
                    req.job_id,
                    req.aisle,
                    tracker=tracker,
                    error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                    current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                    message=f"Artifact marker write failed: {marker_e}",
                    metadata={
                        "artifact_upload_completed": True,
                        "marker_write_completed": False,
                        "verification_required": True,
                        "failed_marker": "ARTIFACTS_PUBLISHED",
                        "published_artifact_kinds": sorted(dispatch_result.durable_meta.keys()),
                        "exception_type": type(marker_e).__name__,
                    },
                )
                return True
            try:
                self._state.finalize_success(
                    req.job_id,
                    req.aisle,
                    req.report_path,
                    tracker=tracker,
                    run_metadata=req.pipeline_result.run_metadata,
                    durable_artifacts=dispatch_result.durable_meta,
                )
            except Exception:
                return True
            return False
        published_required = {
            kind for kind in dispatch_result.published_kinds if is_required_artifact_kind(kind)
        }
        failed_required = {
            kind
            for kind in dispatch_result.permanently_failed_kinds
            if is_required_artifact_kind(kind)
        }
        if published_required and failed_required and not dispatch_result.required_complete:
            failed_kind = sorted(failed_required)[0]
            req.exec_log.error(
                "Artifacts",
                f"Partial durable artifact upload: {failed_kind}",
                payload={"failed_kind": failed_kind},
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Durable artifact upload partial failure: {failed_kind}",
                metadata={
                    "failed_kind": failed_kind,
                    "published_artifacts": {
                        kind: dispatch_result.durable_meta[kind]
                        for kind in sorted(published_required)
                        if kind in dispatch_result.durable_meta
                    },
                },
            )
            return True
        if dispatch_result.permanently_failed_kinds:
            failed_entries = list(dispatch_result.failed_entries)
            if not failed_entries and self._artifact_outbox_store is not None:
                from src.application.services.artifact_publication_diagnostics import (
                    failed_outbox_entry_summary,
                )

                for kind in sorted(dispatch_result.permanently_failed_kinds):
                    entry = self._artifact_outbox_store.get_entry(req.job_id, kind)
                    if entry is not None:
                        failed_entries.append(failed_outbox_entry_summary(entry))
            logger.error(
                "artifact.publication.required_permanently_failed job_id=%s failed_kinds=%s failed_entries=%s",
                req.job_id,
                sorted(dispatch_result.permanently_failed_kinds),
                failed_entries,
            )
            req.exec_log.error(
                "Artifacts",
                "Required artifact publication permanently failed",
                payload={
                    "failed_kinds": sorted(dispatch_result.permanently_failed_kinds),
                    "failed_entries": failed_entries,
                },
            )
            self._state.fail_finalization_and_aisle(
                req.job_id,
                req.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message="Required artifact publication permanently failed",
                metadata={
                    "failed_kinds": sorted(dispatch_result.permanently_failed_kinds),
                    "failed_entries": failed_entries,
                    "published_artifact_kinds": sorted(dispatch_result.published_kinds),
                    "verification_required": True,
                },
            )
            return True
        if dispatch_result.retry_scheduled_kinds:
            req.exec_log.info(
                "Artifacts",
                "Durable artifact publication incomplete; autonomous retry scheduled",
                payload={
                    "retry_kinds": sorted(dispatch_result.retry_scheduled_kinds),
                    "published_kinds": sorted(dispatch_result.published_kinds),
                },
            )
            self._state.mark_artifact_publication_retry_pending(
                req.job_id,
                tracker=tracker,
                retry_kinds=dispatch_result.retry_scheduled_kinds,
                published_kinds=dispatch_result.published_kinds,
            )
            return False
        req.exec_log.error("Artifacts", "Required artifact publication produced no durable outputs")
        self._state.fail_finalization_and_aisle(
            req.job_id,
            req.aisle,
            tracker=tracker,
            error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED,
            current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
            message="Required artifact publication produced no durable outputs",
        )
        return True

