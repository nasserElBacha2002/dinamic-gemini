"""Enqueue + process preliminary reconciliations (diagnostic; server authority unchanged)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from src.application.errors import JobNotFoundError
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
    ProcessingAttemptRepository,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.mobile_preliminary_detection_repository import (
    MobilePreliminaryDetectionRepository,
)
from src.application.ports.preliminary_detection_reconciliation_repository import (
    PreliminaryDetectionReconciliationRepository,
    ReconciliationRowVersionConflictError,
    ReconciliationUniqueViolationError,
)
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.preliminary_detection_compare import (
    COMPARISON_VERSION,
    OUTCOME_NOT_COMPARABLE,
    LocalCompareInput,
    RemoteCompareInput,
    compare_preliminary_vs_remote,
)
from src.application.services.reconciliation_content import (
    content_from_row,
    is_terminal_status,
    same_terminal_content,
)
from src.application.services.resolve_comparable_remote_result import (
    NotComparable,
    ResolveComparableRemoteResult,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.preliminary_detection_reconciliations.entities import (
    PreliminaryDetectionReconciliation,
)

logger = logging.getLogger(__name__)

_JOB_TERMINAL = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED, JobStatus.TIMED_OUT}
_MAX_ATTEMPTS = 8
_BACKOFF_SECONDS = (5, 15, 45, 120, 300, 600, 1200, 3600)
_RETENTION_DAYS = 90
_LEASE_SECONDS = 90


@dataclass
class EnqueueReconciliationCommand:
    inventory_id: str
    aisle_id: str
    job_id: str
    enqueue_limit: int = 200


@dataclass
class EnqueueReconciliationResult:
    accepted: bool
    enqueued: int = 0
    already_terminal: int = 0
    reconciliation_ids: list[str] = field(default_factory=list)
    batch_id: str = ""


@dataclass
class ProcessReconciliationBatchResult:
    claimed: int = 0
    completed: int = 0
    not_comparable: int = 0
    retry_scheduled: int = 0
    failed_terminal: int = 0
    conflicts: int = 0


class ReconciliationDisabledError(Exception):
    pass


class ReconciliationConflictError(Exception):
    def __init__(self, message: str = "RECONCILIATION_CONTENT_CONFLICT") -> None:
        super().__init__(message)
        self.code = "RECONCILIATION_CONTENT_CONFLICT"


def _remote_pipeline_version(job: Job) -> str | None:
    if isinstance(job.engine_params_json, dict):
        for key in (
            "pipeline_version",
            "strategy_version",
            "parser_version",
            "configuration_snapshot_version",
        ):
            val = job.engine_params_json.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    if job.prompt_version and str(job.prompt_version).strip():
        return str(job.prompt_version).strip()
    if job.configuration_snapshot_version is not None:
        return f"snapshot@{job.configuration_snapshot_version}"
    return None


class EnqueuePreliminaryReconciliationsUseCase:
    """Create PENDING rows for drafts in the job asset snapshot (no heavy compare)."""

    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        preliminary_repo: MobilePreliminaryDetectionRepository,
        reconciliation_repo: PreliminaryDetectionReconciliationRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        enabled: bool,
        clock=None,
        comparison_version: str = COMPARISON_VERSION,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._preliminary_repo = preliminary_repo
        self._reconciliation_repo = reconciliation_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._enabled = enabled
        self._clock = clock
        self._comparison_version = comparison_version

    def execute(self, command: EnqueueReconciliationCommand) -> EnqueueReconciliationResult:
        if not self._enabled:
            raise ReconciliationDisabledError()

        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
        )
        job = self._require_job(command.job_id, command.aisle_id)
        if job.status not in _JOB_TERMINAL:
            # Still allow enqueue after terminal only — caller should wait
            raise JobNotFoundError(command.job_id)

        links = self._job_source_asset_repo.list_for_job(command.job_id)
        asset_ids = [lnk.source_asset_id for lnk in links]
        drafts = self._preliminary_repo.list_validated_by_asset_ids(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            asset_ids=asset_ids,
            limit=max(1, min(int(command.enqueue_limit), 500)),
        )

        now = self._now()
        batch_id = str(uuid.uuid4())
        result = EnqueueReconciliationResult(accepted=True, batch_id=batch_id)
        logger.info(
            "reconciliation_enqueued job_id=%s draft_count=%s snapshot_assets=%s",
            command.job_id,
            len(drafts),
            len(asset_ids),
        )

        for draft in drafts:
            if draft.status == "NOT_APPLICABLE":
                continue
            existing = self._reconciliation_repo.get_by_identity(
                preliminary_detection_id=draft.id,
                comparison_version=self._comparison_version,
                job_id=command.job_id,
            )
            if existing is not None:
                if is_terminal_status(existing.reconciliation_status):
                    result.already_terminal += 1
                    result.reconciliation_ids.append(existing.id)
                    continue
                result.reconciliation_ids.append(existing.id)
                continue

            row = PreliminaryDetectionReconciliation(
                id=str(uuid.uuid4()),
                preliminary_detection_id=draft.id,
                asset_id=draft.asset_id,
                remote_result_id=None,
                job_id=command.job_id,
                inventory_id=draft.inventory_id,
                aisle_id=draft.aisle_id,
                client_file_id=draft.client_file_id,
                local_status=draft.status,
                local_internal_code=draft.internal_code,
                local_quantity=draft.quantity,
                remote_status=None,
                remote_internal_code=None,
                remote_quantity=None,
                outcome=OUTCOME_NOT_COMPARABLE,
                not_comparable_reason="PENDING",
                local_parser_version=draft.parser_version,
                local_detector_version=draft.detector_version,
                remote_pipeline_version=None,
                local_detected_at=draft.detected_at,
                remote_completed_at=None,
                compared_at=now,
                comparison_version=self._comparison_version,
                reconciliation_status="PENDING",
                created_at=now,
                updated_at=now,
                remote_result_fingerprint="PENDING",
                expires_at=now + timedelta(days=_RETENTION_DAYS),
            )
            try:
                saved = self._reconciliation_repo.insert(row)
                result.enqueued += 1
                result.reconciliation_ids.append(saved.id)
            except ReconciliationUniqueViolationError:
                raced = self._reconciliation_repo.get_by_identity(
                    preliminary_detection_id=draft.id,
                    comparison_version=self._comparison_version,
                    job_id=command.job_id,
                )
                if raced:
                    result.reconciliation_ids.append(raced.id)
        return result

    def _require_job(self, job_id: str, aisle_id: str) -> Job:
        job = self._job_repo.get_by_id(job_id)
        if job is None or job.target_id != aisle_id:
            raise JobNotFoundError(job_id)
        return job

    def _now(self) -> datetime:
        if self._clock is not None:
            now = self._clock.now()
        else:
            now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now


class ProcessPreliminaryReconciliationsUseCase:
    """Worker: claim due rows, resolve mapping, compare, persist with CAS."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        preliminary_repo: MobilePreliminaryDetectionRepository,
        reconciliation_repo: PreliminaryDetectionReconciliationRepository,
        state_repo: JobAssetProcessingStateRepository,
        attempt_repo: ProcessingAttemptRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        enabled: bool,
        metrics_enabled: bool = False,
        clock=None,
        resolver: ResolveComparableRemoteResult | None = None,
        lease_seconds: int = _LEASE_SECONDS,
        max_attempts: int = _MAX_ATTEMPTS,
    ) -> None:
        self._job_repo = job_repo
        self._preliminary_repo = preliminary_repo
        self._reconciliation_repo = reconciliation_repo
        self._state_repo = state_repo
        self._attempt_repo = attempt_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._enabled = enabled
        self._metrics_enabled = metrics_enabled
        self._clock = clock
        self._resolver = resolver or ResolveComparableRemoteResult()
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts

    def process_due_batch(self, *, limit: int = 50) -> ProcessReconciliationBatchResult:
        if not self._enabled:
            raise ReconciliationDisabledError()
        now = self._now()
        self._reconciliation_repo.release_expired_leases(now=now)
        lease_token = f"recon:{uuid.uuid4().hex[:16]}"
        claimed = self._reconciliation_repo.claim_due(
            lease_token=lease_token,
            lease_expires_at=now + timedelta(seconds=self._lease_seconds),
            now=now,
            limit=max(1, min(limit, 50)),
        )
        result = ProcessReconciliationBatchResult(claimed=len(claimed))
        # Prefetch states/attempts by job to reduce N+1
        by_job: dict[str, list[PreliminaryDetectionReconciliation]] = {}
        for row in claimed:
            by_job.setdefault(row.job_id, []).append(row)

        for job_id, rows in by_job.items():
            job = self._job_repo.get_by_id(job_id)
            if job is None:
                for row in rows:
                    self._fail_terminal(row, "JOB_MISSING", result)
                continue
            snapshot_ids = {
                lnk.source_asset_id for lnk in self._job_source_asset_repo.list_for_job(job_id)
            }
            states = {s.asset_id: s for s in self._state_repo.list_by_job(job_id)}
            attempts_by_asset: dict[str, list] = {}
            for a in self._attempt_repo.list_by_job(job_id):
                attempts_by_asset.setdefault(a.asset_id, []).append(a)

            pipeline_version = _remote_pipeline_version(job)
            for row in rows:
                self._process_one(
                    row=row,
                    job=job,
                    snapshot_ids=snapshot_ids,
                    state=states.get(row.asset_id),
                    attempts=attempts_by_asset.get(row.asset_id, []),
                    pipeline_version=pipeline_version,
                    result=result,
                )

        if self._metrics_enabled:
            logger.info(
                "reconciliation_batch_metrics claimed=%s completed=%s not_comparable=%s "
                "retry=%s failed=%s conflicts=%s",
                result.claimed,
                result.completed,
                result.not_comparable,
                result.retry_scheduled,
                result.failed_terminal,
                result.conflicts,
            )
        return result

    def purge_expired(self, *, limit: int = 500) -> int:
        deleted = self._reconciliation_repo.delete_expired(now=self._now(), limit=limit)
        if deleted:
            logger.info("reconciliation_purged count=%s", deleted)
        return deleted

    def _process_one(
        self,
        *,
        row: PreliminaryDetectionReconciliation,
        job: Job,
        snapshot_ids: set[str],
        state,
        attempts,
        pipeline_version: str | None,
        result: ProcessReconciliationBatchResult,
    ) -> None:
        logger.info(
            "reconciliation_started reconciliation_id=%s preliminary_id=%s",
            row.id,
            row.preliminary_detection_id,
        )
        local = _LocalFromRow(row)

        resolved = self._resolver.execute(
            local_status=local.status,
            local_parser_version=local.parser_version,
            local_detector_version=local.detector_version,
            job_terminal=job.status in _JOB_TERMINAL,
            job_status=job.status,
            asset_in_job_snapshot=row.asset_id in snapshot_ids,
            state=state,
            attempts=attempts,
            remote_pipeline_version=pipeline_version,
        )
        now = self._now()

        if isinstance(resolved, NotComparable):
            if resolved.retryable and row.attempt_count < self._max_attempts:
                self._schedule_retry(row, resolved.reason, result)
                return
            if resolved.retryable and row.attempt_count >= self._max_attempts:
                self._fail_terminal(row, resolved.reason, result)
                return
            updated = self._build_terminal(
                row,
                now=now,
                outcome=OUTCOME_NOT_COMPARABLE,
                reason=resolved.reason,
                status="NOT_COMPARABLE",
                remote_result_id=None,
                remote_status=state.status.value if state else None,
                remote_code=None,
                remote_qty=None,
                remote_completed_at=state.finished_at if state else None,
                pipeline_version=pipeline_version,
                fingerprint="NONE",
            )
            self._persist_terminal(row, updated, result, bucket="not_comparable")
            logger.info(
                "reconciliation_not_comparable reconciliation_id=%s reason=%s",
                row.id,
                resolved.reason,
            )
            return

        comparison = compare_preliminary_vs_remote(
            LocalCompareInput(
                status=local.status,
                internal_code=local.internal_code,
                quantity=local.quantity,
                candidate_count=0,
            ),
            RemoteCompareInput(
                status=resolved.status,
                internal_code=resolved.internal_code,
                quantity=resolved.quantity,
                ambiguous=resolved.ambiguous,
            ),
        )
        updated = self._build_terminal(
            row,
            now=now,
            outcome=comparison.outcome,
            reason=None,
            status="COMPLETED",
            remote_result_id=resolved.remote_result_id,
            remote_status=resolved.status,
            remote_code=comparison.remote_code,
            remote_qty=comparison.remote_quantity,
            remote_completed_at=resolved.completed_at,
            pipeline_version=resolved.pipeline_version or pipeline_version,
            fingerprint=resolved.fingerprint,
            local_code=comparison.local_code,
            local_qty=comparison.local_quantity,
        )
        self._persist_terminal(row, updated, result, bucket="completed")
        logger.info(
            "reconciliation_completed reconciliation_id=%s outcome=%s",
            row.id,
            comparison.outcome,
        )

    def _build_terminal(
        self,
        row: PreliminaryDetectionReconciliation,
        *,
        now: datetime,
        outcome: str,
        reason: str | None,
        status: str,
        remote_result_id: str | None,
        remote_status: str | None,
        remote_code: str | None,
        remote_qty: int | None,
        remote_completed_at: datetime | None,
        pipeline_version: str | None,
        fingerprint: str,
        local_code: str | None = None,
        local_qty: int | None = None,
    ) -> PreliminaryDetectionReconciliation:
        return replace(
            row,
            remote_result_id=remote_result_id,
            remote_result_fingerprint=fingerprint,
            local_internal_code=local_code if local_code is not None else row.local_internal_code,
            local_quantity=local_qty if local_qty is not None else row.local_quantity,
            remote_status=remote_status,
            remote_internal_code=remote_code,
            remote_quantity=remote_qty,
            outcome=outcome,
            not_comparable_reason=reason,
            remote_pipeline_version=pipeline_version,
            remote_completed_at=remote_completed_at,
            compared_at=now,
            reconciliation_status=status,
            lease_token=None,
            lease_expires_at=None,
            next_retry_at=None,
            last_error_code=None,
            updated_at=now,
        )

    def _persist_terminal(
        self,
        previous: PreliminaryDetectionReconciliation,
        updated: PreliminaryDetectionReconciliation,
        result: ProcessReconciliationBatchResult,
        *,
        bucket: str,
    ) -> None:
        # Terminal immutability: if already terminal with same content, skip; if different → conflict
        if is_terminal_status(previous.reconciliation_status):
            if same_terminal_content(content_from_row(previous), content_from_row(updated)):
                return
            result.conflicts += 1
            logger.info(
                "reconciliation_conflict reconciliation_id=%s",
                previous.id,
            )
            return
        try:
            self._reconciliation_repo.update_if_version(
                updated, expected_version=previous.row_version
            )
        except ReconciliationRowVersionConflictError:
            result.conflicts += 1
            return
        if bucket == "completed":
            result.completed += 1
        else:
            result.not_comparable += 1

    def _schedule_retry(
        self,
        row: PreliminaryDetectionReconciliation,
        reason: str,
        result: ProcessReconciliationBatchResult,
    ) -> None:
        now = self._now()
        idx = min(max(row.attempt_count - 1, 0), len(_BACKOFF_SECONDS) - 1)
        next_at = now + timedelta(seconds=_BACKOFF_SECONDS[idx])
        updated = replace(
            row,
            reconciliation_status="RETRY_SCHEDULED",
            next_retry_at=next_at,
            last_error_code=reason,
            lease_token=None,
            lease_expires_at=None,
            updated_at=now,
            not_comparable_reason=reason,
            outcome=OUTCOME_NOT_COMPARABLE,
        )
        try:
            self._reconciliation_repo.update_if_version(updated, expected_version=row.row_version)
            result.retry_scheduled += 1
            logger.info(
                "reconciliation_retry reconciliation_id=%s reason=%s",
                row.id,
                reason,
            )
        except ReconciliationRowVersionConflictError:
            result.conflicts += 1

    def _fail_terminal(
        self,
        row: PreliminaryDetectionReconciliation,
        reason: str,
        result: ProcessReconciliationBatchResult,
    ) -> None:
        now = self._now()
        updated = replace(
            row,
            reconciliation_status="FAILED_TERMINAL",
            outcome=OUTCOME_NOT_COMPARABLE,
            not_comparable_reason=reason,
            last_error_code=reason,
            lease_token=None,
            lease_expires_at=None,
            compared_at=now,
            updated_at=now,
        )
        try:
            self._reconciliation_repo.update_if_version(updated, expected_version=row.row_version)
            result.failed_terminal += 1
            logger.info(
                "reconciliation_failed reconciliation_id=%s reason=%s",
                row.id,
                reason,
            )
        except ReconciliationRowVersionConflictError:
            result.conflicts += 1

    def _now(self) -> datetime:
        if self._clock is not None:
            now = self._clock.now()
        else:
            now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now


@dataclass
class _LocalFromRow:
    status: str
    internal_code: str | None
    quantity: int | None
    parser_version: str | None
    detector_version: str | None

    def __init__(self, row: PreliminaryDetectionReconciliation) -> None:
        self.status = row.local_status
        self.internal_code = row.local_internal_code
        self.quantity = row.local_quantity
        self.parser_version = row.local_parser_version
        self.detector_version = row.local_detector_version


# Backward-compatible alias used by routes/tests during transition
class ReconcilePreliminaryDetectionsUseCase:
    """POST facade: enqueue PENDING rows then optionally process a small batch."""

    def __init__(
        self,
        *,
        enqueue: EnqueuePreliminaryReconciliationsUseCase,
        process: ProcessPreliminaryReconciliationsUseCase,
        process_inline_limit: int = 0,
    ) -> None:
        self._enqueue = enqueue
        self._process = process
        self._process_inline_limit = process_inline_limit

    def execute(self, command: EnqueueReconciliationCommand) -> EnqueueReconciliationResult:
        out = self._enqueue.execute(command)
        if self._process_inline_limit > 0:
            self._process.process_due_batch(limit=self._process_inline_limit)
        return out
