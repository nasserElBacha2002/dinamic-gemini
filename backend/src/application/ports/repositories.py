"""
Repository ports — v3.0 (Documento técnico §9.1).

Use cases depend on these abstractions; infrastructure provides SQL (or other) implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any, Literal, Union

from src.application.ports.contracts import PositionListQuery
from src.application.ports.rollup_contracts import AisleAssetRollup
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.client.entities import Client
from src.domain.client_supplier.entities import ClientSupplier
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.domain.client_supplier.reference_image import SupplierReferenceImage
from src.domain.evidence.entities import Evidence
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.claim import JobClaimResult, StaleReclaimResult
from src.domain.jobs.entities import Job
from src.domain.jobs.lease import JobLease, LeaseRenewalResult, LeaseWriteResult
from src.domain.labels.entities import FinalCountRecord, NormalizedLabel, RawLabel
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.result_evidence.entities import ResultEvidenceRecord
from src.domain.reviews.entities import ReviewAction


class _JobIdFilterUnset:
    """Pass as ``job_id`` to ``list_by_aisle`` to omit a ``job_id`` predicate (all rows for aisle)."""


JOB_ID_FILTER_UNSET = _JobIdFilterUnset()

LabelJobScope = Union[str, Literal["all"], None]
"""``job_id`` filter for label/count repositories: ``\"all\"`` = no filter; ``None`` = ``IS NULL``; else equality."""


class InventoryRepository(ABC):
    @abstractmethod
    def save(self, inventory: Inventory) -> None: ...

    @abstractmethod
    def get_by_id(self, inventory_id: str) -> Inventory | None: ...

    @abstractmethod
    def list_all(self) -> Sequence[Inventory]:
        """Return active inventories (exclude soft-deleted). Order is implementation-defined."""
        ...

    @abstractmethod
    def compare_and_set_status(
        self,
        inventory_id: str,
        *,
        expected_current: InventoryStatus,
        new_status: InventoryStatus,
        updated_at: datetime,
        completed_at: datetime | None,
    ) -> bool:
        """Atomically set status when current row status equals ``expected_current``.

        Returns True if the row was updated. Implementations MUST provide a true
        compare-and-set (SQL ``UPDATE … WHERE status = ?``, or an in-process lock).
        There is no non-atomic read/check/save default.
        """
        ...


class ClientRepository(ABC):
    @abstractmethod
    def save(self, client: Client) -> None: ...

    @abstractmethod
    def get_by_id(self, client_id: str) -> Client | None: ...

    @abstractmethod
    def list_all(self) -> Sequence[Client]:
        """Return all clients. Order is implementation-defined (SQL impl: created_at DESC)."""
        ...

    @abstractmethod
    def get_by_ids(self, client_ids: Sequence[str]) -> dict[str, Client]:
        """Batch load clients by id (dedupe; empty input → empty dict; one query in SQL)."""
        ...


class ClientSupplierRepository(ABC):
    @abstractmethod
    def save(self, supplier: ClientSupplier) -> None: ...

    @abstractmethod
    def get_by_id(self, supplier_id: str) -> ClientSupplier | None: ...

    @abstractmethod
    def get_by_client_and_name(self, client_id: str, name: str) -> ClientSupplier | None: ...

    @abstractmethod
    def list_by_client(self, client_id: str) -> Sequence[ClientSupplier]:
        """Return suppliers for one client. Order is implementation-defined (SQL impl: created_at DESC)."""
        ...

    @abstractmethod
    def get_by_ids(self, supplier_ids: Sequence[str]) -> dict[str, ClientSupplier]:
        """Batch load suppliers by id (dedupe; empty input → empty dict; one query in SQL)."""
        ...

    @abstractmethod
    def get_by_client_and_ids(
        self, client_id: str, supplier_ids: Sequence[str]
    ) -> dict[str, ClientSupplier]:
        """Batch load suppliers owned by ``client_id`` (cross-client ids omitted)."""
        ...


class AisleRepository(ABC):
    @abstractmethod
    def save(self, aisle: Aisle) -> None: ...

    @abstractmethod
    def get_by_id(self, aisle_id: str) -> Aisle | None: ...

    @abstractmethod
    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        """Return aisles for the given inventory. Order is implementation-defined (SQL impl: created_at DESC)."""
        ...

    def list_by_inventories(self, inventory_ids: Sequence[str]) -> Sequence[Aisle]:
        """Batch aisles for many inventories. SQL/Memory override with one query; default loops for stubs."""
        out: list[Aisle] = []
        for inventory_id in {iid for iid in inventory_ids if iid}:
            out.extend(self.list_by_inventory(inventory_id))
        return out

    @abstractmethod
    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        """Return the aisle with the given code in the given inventory, or None. Used for duplicate checks."""
        ...


class SourceAssetRepository(ABC):
    @abstractmethod
    def save(self, asset: SourceAsset) -> None: ...

    @abstractmethod
    def get_by_id(self, asset_id: str) -> SourceAsset | None: ...

    def get_by_ids(self, asset_ids: Sequence[str]) -> dict[str, SourceAsset]:
        """Batch load source assets; implementations should override to avoid N+1 I/O."""
        return {
            asset_id: asset
            for asset_id in dict.fromkeys(asset_ids)
            if (asset := self.get_by_id(asset_id)) is not None
        }

    @abstractmethod
    def delete_by_id(self, asset_id: str) -> bool:
        """Delete the row by primary key. Returns True if a row was removed."""

    @abstractmethod
    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]: ...

    @abstractmethod
    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> dict[str, AisleAssetRollup]:
        """Return upload count and latest ``uploaded_at`` per aisle id (missing aisles omitted or zero)."""
        ...

    @abstractmethod
    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> SourceAsset | None:
        """Return the asset linked to this capture item id, if any (G5 idempotency)."""
        ...

    @abstractmethod
    def get_by_upload_idempotency_key(
        self,
        aisle_id: str,
        upload_batch_id: str,
        upload_client_file_id: str,
    ) -> SourceAsset | None:
        """Return the asset for this aisle + client batch/file id pair, if any."""
        ...

    def get_by_ordered_session_and_client_image_id(
        self,
        session_id: str,
        client_image_id: str,
    ) -> SourceAsset | None:
        """Return the asset for this ordered session + client_image_id, if any."""
        return None

    def get_by_ordered_session_and_sequence(
        self,
        session_id: str,
        sequence_number: int,
    ) -> SourceAsset | None:
        """Return the asset for this ordered session + sequence_number, if any."""
        return None


class PositionRepository(ABC):
    @abstractmethod
    def save(self, position: Position) -> None: ...

    @abstractmethod
    def get_by_id(self, position_id: str) -> Position | None: ...

    @abstractmethod
    def list_by_aisle(
        self,
        aisle_id: str,
        status: str | None = None,
        needs_review: bool | None = None,
        min_confidence: float | None = None,
        sku_filter: str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
        job_id: str | None | _JobIdFilterUnset = JOB_ID_FILTER_UNSET,
    ) -> Sequence[Position]:
        """List positions for an aisle with optional filters and pagination (§9.7).
        sku_filter: when set, only positions that have at least one product_record with
        sku containing this string (substring match) are returned. In-memory impl may ignore it.
        job_id: ``JOB_ID_FILTER_UNSET`` (default) = all positions in the aisle (every run slice);
        ``None`` = legacy ``job_id IS NULL``; ``str`` = that inventory job only. Phase 1 callers that
        need one run must pass a concrete ``job_id``."""
        ...

    @abstractmethod
    def list_by_aisle_query(
        self, aisle_id: str, query: PositionListQuery | None = None
    ) -> Sequence[Position]:
        """List positions for an aisle using optional PositionListQuery. Default query implies page=1, page_size=25."""
        ...

    @abstractmethod
    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        """List positions for multiple aisles (e.g. for metrics)."""
        ...


class ProductRecordRepository(ABC):
    @abstractmethod
    def save(self, product: ProductRecord) -> None: ...

    @abstractmethod
    def get_by_id(self, product_id: str) -> ProductRecord | None: ...

    @abstractmethod
    def list_by_position(self, position_id: str) -> Sequence[ProductRecord]: ...

    def list_by_position_ids(self, position_ids: Sequence[str]) -> Sequence[ProductRecord]:
        """Product rows for any ``position_id`` in ``position_ids`` (empty → empty).

        Default: one ``list_by_position`` per **distinct** id (legacy-compatible). SQL/memory
        implementations override with a single batch query / scan.
        """
        if not position_ids:
            return []
        out: list[ProductRecord] = []
        for pid in dict.fromkeys(position_ids):
            out.extend(self.list_by_position(pid))
        return out


class EvidenceRepository(ABC):
    @abstractmethod
    def save(self, evidence: Evidence) -> None: ...

    @abstractmethod
    def get_by_id(self, evidence_id: str) -> Evidence | None: ...

    @abstractmethod
    def list_by_entity(self, entity_type: str, entity_id: str) -> Sequence[Evidence]: ...


class ReviewActionRepository(ABC):
    @abstractmethod
    def save(self, review: ReviewAction) -> None: ...

    @abstractmethod
    def list_by_position(self, position_id: str) -> Sequence[ReviewAction]: ...


class JobRepository(ABC):
    @abstractmethod
    def save(self, job: Job) -> None: ...

    @abstractmethod
    def get_by_id(self, job_id: str) -> Job | None: ...

    @abstractmethod
    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        """Return the most recently updated (or created) job for the given target, or None."""
        ...

    @abstractmethod
    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> dict[str, Job]:
        """Return the latest job per target_id for the given target_type. Keys are target_id; only one job per target (the latest by updated_at, then created_at). Missing targets are omitted from the dict."""
        ...

    @abstractmethod
    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        """Jobs for one target, newest first (``updated_at DESC``, ``created_at DESC``).

        The default ``limit=50`` is for UI/history browsing only. Never use this method
        (or its limit) for financial cost aggregation.
        """

    @abstractmethod
    def list_jobs_for_targets(
        self,
        target_type: str,
        target_ids: Sequence[str],
        *,
        job_type: str | None = None,
    ) -> Sequence[Job]:
        """Return **all** jobs for the given targets (batch / financial reads).

        Implementations must:
        - Deduplicate ``target_ids`` (order-preserving) before querying.
        - Return every matching job (no per-target history cap, no ``TOP``/``ROW_NUMBER`` truncations).
        - Avoid N+1 (no fan-out to ``list_jobs_for_target``).
        - For SQL Server, batch ``IN`` lists to stay under parameter limits without truncating jobs.
        - Deduplicate result rows by ``job.id`` when merging batches.
        """

    def list_all_jobs(self) -> Sequence[Job]:
        """Bulk read for analytics / ops. Implementations must scan ``inventory_jobs``.

        The abstract default raises so ops CLIs cannot silently scan zero rows.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.list_all_jobs is required for operational scans"
        )

    def get_by_ordered_capture_session(
        self, ordered_capture_session_id: str, *, sequence_version: int
    ) -> Job | None:
        """Return the job pinned to ``(ordered_capture_session_id, sequence_version)``, or None.

        Required on SqlJobRepository and MemoryJobRepository (Phase 1 ordered capture).
        """
        raise NotImplementedError(
            f"{type(self).__name__}.get_by_ordered_capture_session is required "
            "for ordered-capture process idempotency"
        )

    def create_or_get_for_ordered_session(self, job: Job) -> tuple[Job, bool]:
        """Insert job; on unique ``(session, version)`` return existing.

        Returns ``(job, created)``. Requires ``job.ordered_capture_session_id`` and
        ``job.sequence_version`` set. Required on SqlJobRepository and MemoryJobRepository.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.create_or_get_for_ordered_session is required "
            "for ordered-capture process idempotency"
        )

    @abstractmethod
    def list_jobs_by_retry_of(self, retry_of_job_id: str) -> Sequence[Job]:
        """Return jobs whose ``retry_of_job_id`` equals ``retry_of_job_id`` (0 or 1 expected)."""
        ...

    @abstractmethod
    def list_jobs_for_ops_scan(
        self,
        *,
        limit: int = 200,
        statuses: Sequence[str] | None = None,
    ) -> Sequence[Job]:
        """Bounded ops scan (newest first). Must not return silently empty when unsupported."""
        ...

    def merge_result_json(self, job_id: str, patch: dict[str, Any]) -> Job | None:
        """Merge top-level keys into ``job.result_json`` without dropping sibling keys.

        Default implementation is a read-modify-write via ``get_by_id`` + ``save``.
        SQL implementations should override with a row lock / ``JSON_MODIFY`` so concurrent
        writers of other keys (costs, durable artifacts, etc.) are not wiped.
        """
        job = self.get_by_id(job_id)
        if job is None:
            return None
        merged = dict(job.result_json or {})
        merged.update(patch)
        job.result_json = merged
        self.save(job)
        return job

    @abstractmethod
    def try_claim_starting_to_running(
        self,
        job_id: str,
        *,
        now: datetime,
        claim_owner_id: str,
        aisle_id: str,
        lease_duration_seconds: int = 60,
    ) -> JobClaimResult:
        """Atomic STARTING → RUNNING claim with aisle PROCESSING in the same transaction.

        ``claim_owner_id`` must be a non-empty worker token (never ``execution_id``).
        Phase 3: also acquires a lease (fencing token incremented, expiry set from
        ``lease_duration_seconds``) and attaches it to the returned ``JobClaimResult.lease``.
        """

    @abstractmethod
    def renew_lease(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        """Extend ``lease_expires_at`` for an active lease (CAS on owner + fencing_token).

        Does not increment the fencing token.
        """

    @abstractmethod
    def reacquire_expired_lease(
        self,
        job_id: str,
        *,
        now: datetime,
        new_owner_id: str,
        extension_seconds: int,
    ) -> JobClaimResult:
        """Steal an expired RUNNING lease: new owner + fencing_token + 1.

        Test / admin recovery only when production policy is stale-fail (see Phase 3 docs).
        """

    @abstractmethod
    def merge_result_json_if_leased(
        self,
        lease: JobLease,
        patch: dict[str, Any],
        *,
        now: datetime,
    ) -> tuple[LeaseWriteResult, Job | None]:
        """Merge ``result_json`` only while the caller still holds the lease."""

    def touch_heartbeat_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        """Renew lease + update ``last_heartbeat_at`` (same semantics as ``renew_lease`` for Phase 3)."""
        return self.renew_lease(lease, now=now, extension_seconds=extension_seconds)

    @abstractmethod
    def assert_lease(self, lease: JobLease, *, now: datetime) -> LeaseWriteResult:
        """Validate the caller still holds an active lease (no mutation)."""

    @abstractmethod
    def complete_if_leased(
        self,
        lease: JobLease,
        job: Job,
        *,
        now: datetime,
    ) -> LeaseWriteResult:
        """Persist a SUCCEEDED terminal row only while ``lease`` is still held."""

    @abstractmethod
    def fail_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        error_message: str,
        failure_code: str = "PROCESSING_FAILED",
    ) -> LeaseWriteResult:
        """Mark job FAILED only while ``lease`` is still held."""

    @abstractmethod
    def update_finalization_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        mutator: Callable[[Job], None],
    ) -> LeaseWriteResult:
        """Apply finalization-field mutations under lease CAS (no generic save_if_owned)."""

    @abstractmethod
    def acknowledge_cancel_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        reason: str,
    ) -> LeaseWriteResult:
        """Worker acknowledgement: CANCEL_REQUESTED/RUNNING → CANCELED under lease CAS."""

    @abstractmethod
    def try_reclaim_stale_job_and_reconcile_aisle(
        self,
        job_id: str,
        *,
        now: datetime,
        stale_after_seconds: int,
    ) -> StaleReclaimResult:
        """Single-transaction stale CAS fail + aisle reconcile when appropriate."""

    def reclaim_stale_running_jobs(
        self, stale_after_seconds: int, *, batch_size: int = 100
    ) -> int:
        """Fail stale active jobs in bounded batches. Returns jobs reclaimed."""
        return 0

    def list_jobs_for_metrics(
        self,
        *,
        created_from: datetime,
        created_to: datetime,
        job_type: str = "process_aisle",
        target_type: str = "aisle",
        limit: int = 5000,
    ) -> Sequence[Job]:
        """Bounded read for observability metrics (default: filter ``list_all_jobs()`` in memory)."""
        cf = created_from if created_from.tzinfo else created_from.replace(tzinfo=timezone.utc)
        ct = created_to if created_to.tzinfo else created_to.replace(tzinfo=timezone.utc)
        lim = max(1, min(int(limit), 10_000))
        rows: list[Job] = []
        for job in self.list_all_jobs():
            if job.job_type != job_type or job.target_type != target_type:
                continue
            jc = job.created_at
            if jc.tzinfo is None:
                jc = jc.replace(tzinfo=timezone.utc)
            if jc < cf or jc > ct:
                continue
            rows.append(job)
        rows.sort(key=lambda j: j.created_at, reverse=True)
        return rows[:lim]

    def list_jobs_for_metrics_by_finished_at(
        self,
        *,
        finished_from: datetime,
        finished_to: datetime,
        job_type: str = "process_aisle",
        target_type: str = "aisle",
        limit: int = 5000,
    ) -> Sequence[Job]:
        """Bounded read for analytics cost-summary (filter terminal jobs by ``finished_at``)."""
        ff = finished_from if finished_from.tzinfo else finished_from.replace(tzinfo=timezone.utc)
        ft = finished_to if finished_to.tzinfo else finished_to.replace(tzinfo=timezone.utc)
        lim = max(1, min(int(limit), 10_000))
        rows: list[Job] = []
        for job in self.list_all_jobs():
            if job.job_type != job_type or job.target_type != target_type:
                continue
            finished = job.finished_at
            if finished is None:
                continue
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            if finished < ff or finished > ft:
                continue
            rows.append(job)
        rows.sort(key=lambda j: j.finished_at or j.created_at, reverse=True)
        return rows[:lim]


# --- v3.2.3 Label consolidation layers ---


class RawLabelRepository(ABC):
    """Persist and read raw labels (original observations)."""

    @abstractmethod
    def save_many(self, labels: list[RawLabel]) -> None: ...

    @abstractmethod
    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[RawLabel]:
        """Raw labels for scope. ``job_id=\"all\"`` = no filter; ``None`` = legacy null; else one job."""
        ...


class NormalizedLabelRepository(ABC):
    """Persist and read normalized labels (after merge)."""

    @abstractmethod
    def save_many(self, labels: list[NormalizedLabel]) -> None: ...

    @abstractmethod
    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[NormalizedLabel]: ...

    @abstractmethod
    def replace_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> None:
        """Remove normalized labels for scope slice; caller then saves new ones. Idempotent recompute."""
        ...


class FinalCountRepository(ABC):
    """Persist and read final count records (business output)."""

    @abstractmethod
    def save_many(self, records: list[FinalCountRecord]) -> None: ...

    @abstractmethod
    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[FinalCountRecord]: ...

    @abstractmethod
    def list_by_position(self, position_id: str) -> Sequence[FinalCountRecord]:
        """Final count records for one position (e.g. to apply to ProductRecord)."""

    @abstractmethod
    def replace_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> None:
        """Remove final count rows for scope slice; caller then saves new ones."""
        ...


class SupplierReferenceImageRepository(ABC):
    """Persist and list reference images per supplier (Phase C1)."""

    @abstractmethod
    def get_by_id(self, reference_image_id: str) -> SupplierReferenceImage | None:
        """Return one supplier reference image by id, or None when it does not exist."""
        ...

    @abstractmethod
    def create(self, reference_image: SupplierReferenceImage) -> None:
        """Insert one supplier reference image. Must fail if the id already exists."""
        ...

    @abstractmethod
    def create_many(self, reference_images: Sequence[SupplierReferenceImage]) -> None:
        """Insert images atomically if supported. Must fail if any id already exists."""
        ...

    @abstractmethod
    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierReferenceImage]:
        """Return supplier reference images ordered by created_at ASC, id ASC."""
        ...

    @abstractmethod
    def delete(self, reference_image_id: str) -> None:
        """Delete one supplier reference image by id. Idempotent for storage cleanup callers."""
        ...


class SupplierPromptConfigRepository(ABC):
    """Persist and query supplier prompt configurations (Phase D2)."""

    @abstractmethod
    def create(self, config: SupplierPromptConfig) -> SupplierPromptConfig:
        """Insert one supplier prompt config row and return the stored entity."""
        ...

    @abstractmethod
    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierPromptConfig]:
        """Return configs ordered deterministically by provider/scope/version recency."""
        ...

    @abstractmethod
    def list_versions_by_scope(
        self,
        client_supplier_id: str,
        provider_name: str | None,
        model_name: str | None,
    ) -> Sequence[SupplierPromptConfig]:
        """Return versions for one supplier/provider/model scope (newest first)."""
        ...

    @abstractmethod
    def get_by_id(self, config_id: str) -> SupplierPromptConfig | None:
        """Return one config by id, or None."""
        ...

    @abstractmethod
    def get_active_by_scope(
        self,
        client_supplier_id: str,
        provider_name: str | None,
        model_name: str | None,
    ) -> SupplierPromptConfig | None:
        """Return active config for exact scope, or None."""
        ...

    @abstractmethod
    def get_latest_version_number(
        self,
        client_supplier_id: str,
        provider_name: str | None,
        model_name: str | None,
    ) -> int | None:
        """Return max version for exact scope, or None when no rows exist."""
        ...

    @abstractmethod
    def deactivate_scope(
        self,
        client_supplier_id: str,
        provider_name: str | None,
        model_name: str | None,
    ) -> None:
        """Set is_active=0 for all rows in exact scope."""
        ...

    @abstractmethod
    def activate_version(self, config_id: str) -> SupplierPromptConfig | None:
        """Set one version active (and other scope rows inactive), returning the activated row."""
        ...


class ResultEvidenceRepository(ABC):
    """Structural entity traceability evidence rows (Phase 4.6)."""

    @abstractmethod
    def save_many(self, records: list[ResultEvidenceRecord]) -> None:
        """Insert or update evidence rows by primary key."""
        ...

    @abstractmethod
    def delete_by_job_id(self, job_id: str) -> int:
        """Delete all evidence for one job; admin/read helper (prefer delete_for_scope)."""
        ...

    @abstractmethod
    def delete_for_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> int:
        """Delete evidence rows for one operational job result scope."""
        ...

    @abstractmethod
    def list_by_job_id(self, job_id: str) -> Sequence[ResultEvidenceRecord]:
        """Return all evidence rows for a job (any traceability status)."""
        ...

    @abstractmethod
    def list_for_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> Sequence[ResultEvidenceRecord]:
        """Return evidence rows for one operational job result scope."""
        ...

    @abstractmethod
    def list_valid_by_job_id(self, job_id: str) -> Sequence[ResultEvidenceRecord]:
        """Return displayable-valid evidence rows for a job."""
        ...

