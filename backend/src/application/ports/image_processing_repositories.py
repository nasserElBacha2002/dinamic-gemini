"""Ports for Phase 2 image-processing state, attempts, leases, and batch attempts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src.domain.image_processing.batch_processing_attempt import (
    BatchProcessingAttempt,
    BatchProcessingAttemptStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.image_processing.job_processing_lease import JobProcessingLease
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)


@dataclass(frozen=True)
class AssetProgressCounts:
    total: int = 0
    pending: int = 0
    processing: int = 0
    resolved: int = 0
    unrecognized: int = 0
    failed: int = 0
    manual_review: int = 0
    cancelled: int = 0


class JobAssetProcessingStateRepository(ABC):
    @abstractmethod
    def save(self, state: JobAssetProcessingState) -> None: ...

    @abstractmethod
    def get_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> JobAssetProcessingState | None: ...

    @abstractmethod
    def list_by_job(self, job_id: str) -> Sequence[JobAssetProcessingState]: ...

    @abstractmethod
    def try_acquire(
        self,
        job_id: str,
        asset_id: str,
        *,
        expected_statuses: Sequence[JobAssetProcessingStatus],
        next_status: JobAssetProcessingStatus,
        strategy: str,
        now: datetime,
        worker_token: str | None = None,
    ) -> JobAssetProcessingState | None:
        """Atomically transition PENDING -> ``next_status``; return the row from the update only.

        ``FAILED_TECHNICAL`` is a **terminal** status within the same job (Phase 2 corrections
        policy) and must never be included in ``expected_statuses`` by callers — retries of a
        technically-failed asset require a new job, not a same-job re-acquire. Implementations
        must build the returned entity from the rows affected by the atomic UPDATE (SQL:
        ``UPDATE ... OUTPUT inserted.*``), not from a separate follow-up ``SELECT``, so a
        concurrent winner's write can never be misreported as this caller's acquisition.
        """
        ...

    @abstractmethod
    def save_with_ownership(
        self,
        state: JobAssetProcessingState,
        *,
        expected_version: int,
        worker_token: str | None,
    ) -> None:
        """Atomic ``UPDATE ... WHERE version = expected_version`` (+ worker_token when set).

        Raises :class:`src.application.errors.AssetProcessingStateConcurrencyError` when the
        update affects zero rows (lost race, expired lease, or state already finalized by
        another worker). Callers must reload and re-decide rather than blindly retry the same
        write.
        """
        ...

    @abstractmethod
    def aggregate_progress(self, job_id: str) -> AssetProgressCounts: ...

    @abstractmethod
    def list_abandoned_processing(
        self,
        *,
        older_than: datetime,
        limit: int = 100,
        job_id: str | None = None,
        as_of: datetime | None = None,
    ) -> Sequence[JobAssetProcessingState]:
        """Return PROCESSING rows considered abandoned.

        - Rows with ``lease_expires_at``: abandoned when ``lease_expires_at < as_of``
          (defaults to ``older_than`` when ``as_of`` is omitted).
        - Rows without ``lease_expires_at``: abandoned when ``updated_at < older_than``.
        Optional ``job_id`` scopes the scan to one job (orchestrator recovery path).
        """
        ...


class ProcessingAttemptRepository(ABC):
    @abstractmethod
    def save(self, attempt: ProcessingAttempt) -> None: ...

    @abstractmethod
    def get_by_id(self, attempt_id: str) -> ProcessingAttempt | None: ...

    @abstractmethod
    def get_by_unique_key(
        self,
        job_id: str,
        asset_id: str,
        strategy: str,
        attempt_number: int,
    ) -> ProcessingAttempt | None: ...

    @abstractmethod
    def list_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> Sequence[ProcessingAttempt]: ...

    @abstractmethod
    def list_by_job(self, job_id: str) -> Sequence[ProcessingAttempt]: ...

    @abstractmethod
    def next_attempt_number(self, job_id: str, asset_id: str, strategy: str) -> int: ...

    @abstractmethod
    def create_next_attempt(
        self,
        *,
        job_id: str,
        asset_id: str,
        strategy: str,
        status: ProcessingAttemptStatus,
        now: datetime,
        provider: str | None = None,
        model: str | None = None,
        execution_scope: str | None = None,
        configuration_snapshot_version: int | None = None,
        parent_batch_attempt_id: str | None = None,
        batch_execution_id: str | None = None,
        worker_token: str | None = None,
        logical_asset_attempt: bool = True,
    ) -> ProcessingAttempt:
        """Atomically compute the next ``attempt_number`` and insert the row.

        Replaces the ``next_attempt_number()`` + ``save()`` two-step (race-prone under
        concurrent workers). SQL implementations must serialize the read-max + insert
        (``UPDLOCK``/``HOLDLOCK`` or unique-index-violation retry); memory implementation
        is single-process-atomic by construction.
        """
        ...

    @abstractmethod
    def list_started_by_job(self, job_id: str) -> Sequence[ProcessingAttempt]:
        """All STARTED logical attempts for a job (used to close them on recovery)."""
        ...


class JobProcessingLeaseRepository(ABC):
    """Exclusive lease per ``(job_id, strategy, execution_scope)`` guarding one physical batch run."""

    @abstractmethod
    def try_acquire_lease(
        self,
        *,
        job_id: str,
        strategy: str,
        execution_scope: str,
        worker_token: str,
        now: datetime,
        lease_duration_seconds: int,
    ) -> JobProcessingLease | None:
        """Create-or-acquire the lease row for this scope. ``None`` if another worker holds it.

        Idempotent: if no row exists, inserts one directly in ``ACQUIRED`` state owned by
        ``worker_token``. If a row exists in ``AVAILABLE`` (or expired ``ACQUIRED``), atomically
        transitions it to ``ACQUIRED`` for ``worker_token``. If a row exists in a live
        ``ACQUIRED`` state owned by a different token, returns ``None`` without mutating it.
        """
        ...

    @abstractmethod
    def heartbeat(
        self,
        lease_id: str,
        *,
        worker_token: str,
        now: datetime,
        lease_duration_seconds: int,
    ) -> JobProcessingLease | None:
        """Extend ``lease_expires_at``; ``None`` if not owned by ``worker_token`` anymore."""
        ...

    @abstractmethod
    def release(self, lease_id: str, *, worker_token: str, now: datetime) -> None:
        """Return the lease to ``AVAILABLE`` (e.g. cancelled before the provider ran)."""
        ...

    @abstractmethod
    def complete(self, lease_id: str, *, worker_token: str, now: datetime) -> None: ...

    @abstractmethod
    def fail(
        self,
        lease_id: str,
        *,
        worker_token: str,
        now: datetime,
        error_message: str | None = None,
    ) -> None: ...

    @abstractmethod
    def get_by_job_strategy_scope(
        self, job_id: str, strategy: str, execution_scope: str
    ) -> JobProcessingLease | None: ...

    @abstractmethod
    def recover_expired(
        self, *, now: datetime, limit: int = 100
    ) -> Sequence[JobProcessingLease]:
        """Transition expired ``ACQUIRED`` leases back to ``AVAILABLE``; return the recovered rows."""
        ...


class BatchProcessingAttemptRepository(ABC):
    """Physical (one-per-batch-run) execution attempts, distinct from logical per-asset attempts."""

    @abstractmethod
    def create_started(self, attempt: BatchProcessingAttempt) -> BatchProcessingAttempt: ...

    @abstractmethod
    def finalize(
        self,
        attempt_id: str,
        *,
        status: BatchProcessingAttemptStatus,
        now: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> BatchProcessingAttempt | None: ...

    @abstractmethod
    def get_started_by_job(
        self, job_id: str, strategy: str, execution_scope: str
    ) -> Sequence[BatchProcessingAttempt]:
        """``STARTED`` batch attempts for this scope (used to close them on recovery)."""
        ...
