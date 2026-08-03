"""Orchestrate Phase 4 sequential position reconciliation for one job."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    PositionReconciliationAlreadyRunningError,
    PositionReconciliationInputChangedError,
    PositionReconciliationNotReadyError,
)
from src.application.ports.clock import Clock
from src.application.ports.image_position_label_detection_repository import (
    ImagePositionLabelDetectionRepository,
)
from src.application.ports.job_image_coverage_repository import JobImageCoverageRepository
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    SourceAssetRepository,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.position_reconciliation.fingerprint import (
    build_fingerprint_from_frames,
)
from src.application.services.position_reconciliation.job_final_item_result_reader import (
    JobFinalItemResultReader,
)
from src.application.services.position_reconciliation.readiness import (
    PositionReconciliationReadinessPolicy,
)
from src.application.services.position_reconciliation.sequential_reconciler import (
    SequentialPositionReconciler,
)
from src.domain.position_reconciliation.entities import (
    RECONCILIATION_VERSION,
    AssignmentStatus,
    ItemResultRef,
    OrderedImageFrame,
    PositionDetectionRef,
    PositionReconciliation,
    ProductPositionAssignment,
    ReconciliationStatus,
)


@dataclass(frozen=True)
class ReconcileJobPositionsCommand:
    inventory_id: str
    job_id: str
    principal: AccessPrincipal | None = None
    force_new_revision: bool = False
    allow_in_finalization: bool = False


@dataclass(frozen=True)
class ReconcileJobPositionsResult:
    reconciliation: PositionReconciliation
    assignments: tuple[ProductPositionAssignment, ...]
    reused: bool = False
    dry_run: bool = False


class ReconcileJobPositionsUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        source_asset_repo: SourceAssetRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        coverage_repo: JobImageCoverageRepository,
        product_record_repo: ProductRecordRepository,
        detection_repo: ImagePositionLabelDetectionRepository,
        reconciliation_repo: PositionReconciliationRepository,
        clock: Clock,
        position_repo: PositionRepository | None = None,
        readiness_policy: PositionReconciliationReadinessPolicy | None = None,
        final_item_result_reader: JobFinalItemResultReader | None = None,
        access_policy: InventoryAccessPolicy | None = None,
        reconciler: SequentialPositionReconciler | None = None,
        enabled: bool = True,
        persistence_enabled: bool = True,
    ) -> None:
        self._inventories = inventory_repo
        self._aisles = aisle_repo
        self._jobs = job_repo
        self._assets = source_asset_repo
        self._job_assets = job_source_asset_repo
        self._coverage = coverage_repo
        self._products = product_record_repo
        self._detections = detection_repo
        self._reconciliations = reconciliation_repo
        self._positions = position_repo
        self._clock = clock
        self._readiness = readiness_policy or PositionReconciliationReadinessPolicy()
        self._result_reader = final_item_result_reader or JobFinalItemResultReader(
            coverage_repo=coverage_repo,
            product_record_repo=product_record_repo,
        )
        self._access = access_policy
        self._reconciler = reconciler or SequentialPositionReconciler()
        self._enabled = enabled
        self._persistence_enabled = persistence_enabled

    def record_failure(self, *, inventory_id: str, job_id: str, failure_code: str) -> None:
        """Best-effort durable FAILED state for auto-run failures before a RUNNING claim."""

        if not self._persistence_enabled:
            return
        inventory = self._inventories.get_by_id(inventory_id)
        job = self._jobs.get_by_id(job_id)
        if inventory is None or not inventory.client_id or job is None:
            return
        previous = self._reconciliations.get_last_attempt_by_job(job_id)
        now = self._clock.now()
        failed = PositionReconciliation(
            id=str(uuid4()),
            client_id=inventory.client_id,
            inventory_id=inventory_id,
            job_id=job_id,
            ordered_capture_session_id=job.ordered_capture_session_id,
            input_fingerprint=f"failed:{uuid4()}",
            status=ReconciliationStatus.FAILED,
            started_at=now,
            completed_at=now,
            failure_code=failure_code,
            attempt_count=(previous.attempt_count + 1 if previous else 1),
            created_at=now,
            updated_at=now,
            metadata_json={"events": ["POSITION_RECONCILIATION_FAILED"]},
            is_active=False,
        )
        self._reconciliations.record_failed_attempt(failed)

    def _load_frames(
        self,
        *,
        job_id: str,
        aisle_id: str,
        ordered_capture_session_id: str | None,
        links,
    ) -> tuple[list[OrderedImageFrame], list]:
        asset_ids = tuple(link.source_asset_id for link in links)
        source_assets = self._assets.get_by_ids(asset_ids)
        result_refs = self._result_reader.list_for_job(
            job_id=job_id,
            aisle_id=aisle_id,
            asset_ids=asset_ids,
        )
        results_by_asset: dict[str, list[ItemResultRef]] = {}
        for ref in result_refs:
            results_by_asset.setdefault(ref.source_asset_id, []).append(
                ItemResultRef(result_id=ref.result_id)
            )
        detections = list(self._detections.list_by_job(job_id))
        detections_by_asset: dict[str, list[PositionDetectionRef]] = {}
        for detection in detections:
            detections_by_asset.setdefault(detection.source_asset_id, []).append(
                PositionDetectionRef(
                    id=detection.id,
                    client_id=detection.client_id,
                    detection_status=detection.detection_status,
                    signature_status=detection.signature_status,
                    position_label_id=detection.position_label_id,
                    position_name_snapshot=detection.position_name_snapshot,
                    detector_version=detection.detector_version,
                )
            )
        frames: list[OrderedImageFrame] = []
        sequence_sources: list[str] = []
        for link in links:
            asset = source_assets.get(link.source_asset_id)
            sequence_number, sequence_source = self._resolve_sequence_number(
                asset=asset, link=link
            )
            sequence_sources.append(sequence_source)
            frames.append(
                OrderedImageFrame(
                    source_asset_id=link.source_asset_id,
                    client_image_id=asset.upload_client_file_id if asset else None,
                    ordered_capture_session_id=(
                        asset.ordered_capture_session_id
                        if asset
                        else ordered_capture_session_id
                    ),
                    sequence_number=sequence_number,
                    item_results=tuple(results_by_asset.get(link.source_asset_id, ())),
                    position_detections=tuple(
                        detections_by_asset.get(link.source_asset_id, ())
                    ),
                )
            )
        frames = self._normalize_system_upload_frame_order(frames, sequence_sources)
        return frames, detections

    @staticmethod
    def _resolve_sequence_number(*, asset, link) -> tuple[int | None, str]:
        """Prefer capture sequence; fall back to job link order for system uploads.

        Mobile ordered capture sets ``sequence_number``. Web/system aisle uploads often
        only populate ``job_source_assets.position_order`` (0-based upload order). Without
        that fallback every product stays ``UNASSIGNED_UNORDERED_ASSET`` and photo↔position
        never appears in assignments.

        Returns ``(sequence_number, source)`` where source is one of
        ``capture`` | ``link`` | ``position_order`` | ``none``.
        """
        if asset is not None and asset.sequence_number is not None:
            return int(asset.sequence_number), "capture"
        if link.sequence_number is not None:
            return int(link.sequence_number), "link"
        if getattr(link, "position_order", None) is not None:
            return int(link.position_order), "position_order"
        return None, "none"

    @staticmethod
    def _frame_can_establish_position(frame: OrderedImageFrame) -> bool:
        for detection in frame.position_detections:
            status = (
                detection.detection_status.value
                if hasattr(detection.detection_status, "value")
                else str(detection.detection_status)
            ).strip().upper()
            if status in {"VALID", "LEGACY_UNSIGNED_REQUIRES_REVIEW"} and detection.position_label_id:
                return True
        return False

    @classmethod
    def _normalize_system_upload_frame_order(
        cls,
        frames: list[OrderedImageFrame],
        sequence_sources: list[str],
    ) -> list[OrderedImageFrame]:
        """For web uploads (position_order only), place position photos before item photos.

        Capture/link sequences are authoritative and must not be rewritten. When every
        sequenced frame came from upload ``position_order``, arbitrary file-picker order
        (item then position) would leave products ``UNASSIGNED_NO_PREVIOUS_POSITION``.
        """
        if not frames:
            return frames
        if any(source in {"capture", "link"} for source in sequence_sources):
            return frames
        if not all(source in {"position_order", "none"} for source in sequence_sources):
            return frames

        ordered = [f for f in frames if f.sequence_number is not None]
        unordered = [f for f in frames if f.sequence_number is None]
        if not ordered:
            return frames

        with_position = sorted(
            (f for f in ordered if cls._frame_can_establish_position(f)),
            key=lambda f: (int(f.sequence_number or 0), f.source_asset_id),
        )
        without_position = sorted(
            (f for f in ordered if not cls._frame_can_establish_position(f)),
            key=lambda f: (int(f.sequence_number or 0), f.source_asset_id),
        )
        resequenced: list[OrderedImageFrame] = []
        for index, frame in enumerate(with_position + without_position):
            resequenced.append(replace(frame, sequence_number=index))
        return resequenced + unordered

    def execute(self, command: ReconcileJobPositionsCommand) -> ReconcileJobPositionsResult:
        if not self._enabled:
            raise PositionReconciliationNotReadyError("Position reconciliation is disabled")
        if command.principal is not None and self._access is not None:
            self._access.require_inventory(command.inventory_id, command.principal)

        inventory = self._inventories.get_by_id(command.inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        if not inventory.client_id:
            raise PositionReconciliationNotReadyError("Inventory has no client scope")
        job = self._jobs.get_by_id(command.job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {command.job_id}")
        if job.target_type != "aisle":
            raise JobDoesNotBelongToAisleError("Position reconciliation requires an aisle job")
        aisle = self._aisles.get_by_id(job.target_id)
        if aisle is None or aisle.inventory_id != command.inventory_id:
            raise JobDoesNotBelongToAisleError(
                f"Job {command.job_id} is outside inventory {command.inventory_id}"
            )

        links = self._job_assets.list_for_job(command.job_id)
        self._readiness.require_ready(
            job,
            inventory_id=command.inventory_id,
            aisle=aisle,
            links=links,
            allow_in_finalization=command.allow_in_finalization,
        )
        frames, detections = self._load_frames(
            job_id=command.job_id,
            aisle_id=job.target_id,
            ordered_capture_session_id=job.ordered_capture_session_id,
            links=links,
        )

        sessions = {
            frame.ordered_capture_session_id for frame in frames if frame.ordered_capture_session_id
        }
        session_id = next(iter(sessions), job.ordered_capture_session_id)
        fingerprint = build_fingerprint_from_frames(
            frames,
            sequence_version=job.sequence_version,
        )
        active = self._reconciliations.get_published_by_job(command.job_id)
        if active is not None and active.status is ReconciliationStatus.COMPLETED:
            if active.input_fingerprint == fingerprint and not command.force_new_revision:
                return ReconcileJobPositionsResult(
                    reconciliation=active,
                    assignments=tuple(
                        self._reconciliations.list_active_assignments(command.job_id)
                    ),
                    reused=True,
                )
            if not command.force_new_revision:
                raise PositionReconciliationInputChangedError(
                    "Completed reconciliation inputs changed; retry explicitly"
                )

        decisions = self._reconciler.reconcile(frames, expected_client_id=inventory.client_id)
        now = self._clock.now()
        reconciliation = PositionReconciliation(
            id=str(uuid4()),
            client_id=inventory.client_id,
            inventory_id=inventory.id,
            job_id=job.id,
            ordered_capture_session_id=session_id,
            input_fingerprint=fingerprint,
            status=ReconciliationStatus.RUNNING,
            started_at=now,
            attempt_count=(active.attempt_count + 1 if active else 1),
            created_at=now,
            updated_at=now,
        )
        if self._persistence_enabled:
            claimed = self._reconciliations.begin_or_get_running(reconciliation)
            if claimed.id != reconciliation.id:
                if (
                    claimed.status is ReconciliationStatus.COMPLETED
                    and claimed.input_fingerprint == fingerprint
                ):
                    return ReconcileJobPositionsResult(
                        reconciliation=claimed,
                        assignments=tuple(
                            self._reconciliations.list_active_assignments(command.job_id)
                        ),
                        reused=True,
                    )
                raise PositionReconciliationAlreadyRunningError(
                    f"Reconciliation is already running for job {command.job_id}"
                )

        completed_at = self._clock.now()
        assignments = tuple(
            ProductPositionAssignment(
                id=str(uuid4()),
                client_id=inventory.client_id,
                inventory_id=inventory.id,
                job_id=job.id,
                result_id=decision.result_id,
                source_asset_id=decision.source_asset_id,
                ordered_capture_session_id=decision.ordered_capture_session_id,
                sequence_number=decision.sequence_number,
                position_label_id=decision.position_label_id,
                position_name_snapshot=decision.position_name_snapshot,
                source_detection_id=decision.source_detection_id,
                assignment_status=decision.assignment_status,
                assignment_reason=decision.assignment_reason,
                assignment_source=decision.assignment_source,
                reconciliation_id=reconciliation.id,
                reconciliation_version=RECONCILIATION_VERSION,
                created_at=completed_at,
                updated_at=completed_at,
            )
            for decision in decisions
        )
        reconciliation.status = ReconciliationStatus.COMPLETED
        reconciliation.completed_at = completed_at
        reconciliation.updated_at = completed_at
        reconciliation.assigned_count = sum(
            row.assignment_status is AssignmentStatus.ASSIGNED_AUTOMATIC for row in assignments
        )
        reconciliation.unassigned_count = len(assignments) - reconciliation.assigned_count
        ordered_sequences = sorted(
            {int(frame.sequence_number) for frame in frames if frame.sequence_number is not None}
        )
        reconciliation.sequence_gap_count = sum(
            current > previous + 1
            for previous, current in zip(ordered_sequences, ordered_sequences[1:], strict=False)
        )
        reconciliation.metadata_json = {
            "events": ["POSITION_RECONCILIATION_COMPLETED"],
            "detector_versions": sorted({row.detector_version for row in detections}),
        }
        if not self._persistence_enabled:
            reconciliation.is_active = False
            reconciliation.metadata_json["dry_run"] = True
            return ReconcileJobPositionsResult(
                reconciliation,
                assignments,
                dry_run=True,
            )

        publish_job = self._jobs.get_by_id(command.job_id)
        if publish_job is None:
            reconciliation.status = ReconciliationStatus.FAILED
            reconciliation.failure_code = PositionReconciliationInputChangedError.code
            reconciliation.completed_at = self._clock.now()
            reconciliation.updated_at = reconciliation.completed_at
            self._reconciliations.record_failed_attempt(reconciliation)
            raise PositionReconciliationInputChangedError(
                "Job disappeared before reconciliation publication"
            )
        publish_frames, _ = self._load_frames(
            job_id=command.job_id,
            aisle_id=job.target_id,
            ordered_capture_session_id=publish_job.ordered_capture_session_id,
            links=self._job_assets.list_for_job(command.job_id),
        )
        publish_fingerprint = build_fingerprint_from_frames(
            publish_frames,
            sequence_version=publish_job.sequence_version,
        )
        if publish_fingerprint != fingerprint:
            reconciliation.status = ReconciliationStatus.FAILED
            reconciliation.failure_code = PositionReconciliationInputChangedError.code
            reconciliation.completed_at = self._clock.now()
            reconciliation.updated_at = reconciliation.completed_at
            self._reconciliations.record_failed_attempt(reconciliation)
            raise PositionReconciliationInputChangedError(
                "Position reconciliation inputs changed before publication"
            )
        published = self._reconciliations.publish_completed_revision_atomically(
            reconciliation,
            assignments,
            active.id if active else None,
            expected_input_fingerprint=fingerprint,
        )
        if published.id != reconciliation.id:
            return ReconcileJobPositionsResult(
                published,
                tuple(self._reconciliations.list_active_assignments(command.job_id)),
                reused=True,
            )
        return ReconcileJobPositionsResult(reconciliation, assignments)
