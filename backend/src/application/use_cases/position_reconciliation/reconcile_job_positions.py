"""Orchestrate Phase 4 sequential position reconciliation for one job."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    ProductRecordRepository,
    SourceAssetRepository,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.position_reconciliation.fingerprint import (
    compute_input_fingerprint,
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


@dataclass(frozen=True)
class ReconcileJobPositionsResult:
    reconciliation: PositionReconciliation
    assignments: tuple[ProductPositionAssignment, ...]
    reused: bool = False


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
        previous = self._reconciliations.get_active_by_job(job_id)
        now = datetime.now(timezone.utc)
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
        )
        self._reconciliations.persist_revision_atomically(
            failed, (), previous.id if previous else None
        )

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
        source_assets = {
            link.source_asset_id: self._assets.get_by_id(link.source_asset_id) for link in links
        }
        asset_ids = tuple(link.source_asset_id for link in links)
        positions_by_asset = self._coverage.load_positions_for_assets(
            job_id=command.job_id,
            aisle_id=job.target_id,
            source_asset_ids=asset_ids,
        )
        all_position_ids = [
            position.id for positions in positions_by_asset.values() for position in positions
        ]
        products = self._products.list_by_position_ids(all_position_ids)
        products_by_position: dict[str, list[ItemResultRef]] = {}
        for product in products:
            products_by_position.setdefault(product.position_id, []).append(
                ItemResultRef(result_id=product.id)
            )

        detections = list(self._detections.list_by_job(command.job_id))
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
        for link in links:
            asset = source_assets.get(link.source_asset_id)
            frame_items = tuple(
                item
                for position in positions_by_asset.get(link.source_asset_id, ())
                for item in products_by_position.get(position.id, ())
            )
            frames.append(
                OrderedImageFrame(
                    source_asset_id=link.source_asset_id,
                    client_image_id=(asset.upload_client_file_id if asset is not None else None),
                    ordered_capture_session_id=(
                        asset.ordered_capture_session_id
                        if asset is not None
                        else job.ordered_capture_session_id
                    ),
                    sequence_number=(
                        asset.sequence_number if asset is not None else link.sequence_number
                    ),
                    item_results=frame_items,
                    position_detections=tuple(detections_by_asset.get(link.source_asset_id, ())),
                )
            )

        decisions = self._reconciler.reconcile(frames, expected_client_id=inventory.client_id)
        sessions = {
            frame.ordered_capture_session_id for frame in frames if frame.ordered_capture_session_id
        }
        session_id = next(iter(sessions), job.ordered_capture_session_id)
        detector_version = ",".join(sorted({row.detector_version for row in detections}))
        fingerprint = compute_input_fingerprint(
            ordered_capture_session_id=session_id,
            sequence_version=job.sequence_version,
            position_detection_version=detector_version,
            result_ids=(decision.result_id for decision in decisions),
        )
        active = self._reconciliations.get_active_by_job(command.job_id)
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
            if self._persistence_enabled:
                self._reconciliations.mark_stale(command.job_id)
        if active is not None and active.status is ReconciliationStatus.RUNNING:
            raise PositionReconciliationAlreadyRunningError(
                f"Reconciliation is already running for job {command.job_id}"
            )

        now = datetime.now(timezone.utc)
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

        completed_at = datetime.now(timezone.utc)
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
        if self._persistence_enabled:
            self._reconciliations.persist_revision_atomically(
                reconciliation, assignments, active.id if active else None
            )
        return ReconcileJobPositionsResult(reconciliation, assignments)
