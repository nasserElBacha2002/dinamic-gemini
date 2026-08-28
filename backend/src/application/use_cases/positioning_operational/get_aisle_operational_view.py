"""Get aisle positioning operational view (Phase 7 corrections)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import InventoryNotFoundError
from src.application.ports.client_position_label_repository import (
    ClientPositionLabelRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.image_position_label_detection_repository import (
    ImagePositionLabelDetectionRepository,
)
from src.application.ports.job_image_coverage_repository import JobImageCoverageRepository
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.local_csv_inventory_result_writer import LocalCsvInventoryResultWriter
from src.application.ports.manual_position_override_repository import (
    ManualPositionOverrideRepository,
)
from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
)
from src.application.ports.repositories import (
    InventoryRepository,
    ProductRecordRepository,
)
from src.application.services.aisle_processing_state import resolve_aisle_processing_state
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.position_overrides.effective_position_reader import (
    EffectivePositionReader,
)
from src.application.services.position_reconciliation.job_final_item_result_reader import (
    JobFinalItemResultReader,
)
from src.application.services.position_reconciliation.published_assignment_reader import (
    PublishedPositionAssignmentReader,
)
from src.application.services.positioning_operational.allowed_actions import (
    resolve_positioning_allowed_actions,
)
from src.application.services.positioning_operational.sequence_event_classifier import (
    is_resolved_position_detection,
)
from src.application.services.positioning_operational.warnings_builder import (
    build_operational_warnings,
    is_ambiguous_detection_status,
    is_invalid_detection_status,
    unassigned_buckets_from_assignments,
)
from src.application.use_cases.aisles.get_aisle_processing_status import (
    GetAisleProcessingStatusUseCase,
)
from src.domain.local_csv_import.sources import INGESTION_SOURCE_DINAMIC_SCANNER_TXT
from src.domain.position_overrides.entities import EffectivePositionSource
from src.domain.position_reconciliation.entities import AssignmentStatus, ReconciliationStatus
from src.domain.positioning_operational.entities import (
    AisleOperationalPositioningView,
    PositioningReprocessMode,
)
from src.observability.metrics.instruments import record_positioning_operational_view

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GetAisleOperationalPositioningViewCommand:
    inventory_id: str
    aisle_id: str
    principal: AccessPrincipal
    job_id: str | None = None


def _recon_version_as_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class GetAisleOperationalPositioningViewUseCase:
    def __init__(
        self,
        *,
        status_use_case: GetAisleProcessingStatusUseCase,
        inventory_repo: InventoryRepository,
        access_policy: InventoryAccessPolicy,
        reconciliation_repo: PositionReconciliationRepository,
        detection_repo: ImagePositionLabelDetectionRepository,
        override_repo: ManualPositionOverrideRepository | None,
        label_repo: ClientPositionLabelRepository | None,
        job_source_asset_repo: JobSourceAssetRepository,
        coverage_repo: JobImageCoverageRepository,
        product_record_repo: ProductRecordRepository,
        clock: Clock,
        operational_ux_enabled: bool = True,
        reprocessing_enabled: bool = True,
        recovery_enabled: bool = True,
        overrides_enabled: bool = False,
        enrichment_enabled: bool = True,
        local_csv_result_writer: LocalCsvInventoryResultWriter | None = None,
    ) -> None:
        self._status = status_use_case
        self._inventory_repo = inventory_repo
        self._access = access_policy
        self._reconciliation_repo = reconciliation_repo
        self._detection_repo = detection_repo
        self._override_repo = override_repo
        self._label_repo = label_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._final_results = JobFinalItemResultReader(
            coverage_repo=coverage_repo,
            product_record_repo=product_record_repo,
        )
        self._clock = clock
        self._operational_ux_enabled = bool(operational_ux_enabled)
        self._reprocessing_enabled = bool(reprocessing_enabled)
        self._recovery_enabled = bool(recovery_enabled)
        self._overrides_enabled = bool(overrides_enabled)
        self._enrichment_enabled = bool(enrichment_enabled)
        self._local_csv_result_writer = local_csv_result_writer

    def execute(
        self, command: GetAisleOperationalPositioningViewCommand
    ) -> AisleOperationalPositioningView:
        started = time.monotonic()
        outcome = "ok"
        try:
            return self._execute(command)
        except Exception:
            outcome = "error"
            raise
        finally:
            record_positioning_operational_view(
                outcome=outcome,
                duration_seconds=time.monotonic() - started,
            )

    def _execute(
        self, command: GetAisleOperationalPositioningViewCommand
    ) -> AisleOperationalPositioningView:
        self._access.require_inventory(command.inventory_id, command.principal)
        status = self._status.execute(command.inventory_id, command.aisle_id)
        inventory = self._inventory_repo.get_by_id(command.inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(command.inventory_id)

        processing = resolve_aisle_processing_state(
            latest_job=status.latest_job,
            recent_jobs=status.recent_jobs,
            operational_job_id=status.aisle.operational_job_id,
            clock=self._clock,
        )

        result_job_id = (command.job_id or "").strip() or None
        if result_job_id is None:
            result_job_id = (
                status.aisle.operational_job_id
                or processing.job_id
                or (status.latest_job.id if status.latest_job else None)
            )

        recon = None
        assignments = []
        detections = []
        result_ids: list[str] = []
        unordered = 0
        if result_job_id:
            recon = self._reconciliation_repo.get_published_by_job(result_job_id)
            if recon is None:
                recon = self._reconciliation_repo.get_last_attempt_by_job(result_job_id)
            assignments = list(self._reconciliation_repo.list_active_assignments(result_job_id))
            detections = list(self._detection_repo.list_by_job(result_job_id))
            links = self._job_source_asset_repo.list_for_job(result_job_id)
            asset_ids = tuple(link.source_asset_id for link in links)
            finals = self._final_results.list_for_job(
                job_id=result_job_id,
                aisle_id=command.aisle_id,
                asset_ids=asset_ids,
            )
            result_ids = [row.result_id for row in finals]
            if not result_ids:
                result_ids = [a.result_id for a in assignments if a.result_id]
            unordered = sum(
                1
                for a in assignments
                if (
                    a.assignment_status.value
                    if isinstance(a.assignment_status, AssignmentStatus)
                    else str(a.assignment_status)
                )
                == AssignmentStatus.UNASSIGNED_UNORDERED_ASSET.value
            )

        assigned_automatic = 0
        assigned_manual = 0
        unassigned_automatic = 0
        unassigned_manual = 0
        stale_count = 0
        manual_count = 0
        statuses: list[str] = []

        if result_job_id and result_ids and self._override_repo is not None:
            effective = EffectivePositionReader(
                automatic_reader=PublishedPositionAssignmentReader(
                    reconciliation_repo=self._reconciliation_repo,
                    enrichment_enabled=self._enrichment_enabled,
                ),
                override_repo=self._override_repo,
                label_repo=self._label_repo,
            ).load_for_job(result_job_id, result_ids=result_ids)
            manual_count = sum(1 for v in effective.values() if v.manual_override is not None)
            for view in effective.values():
                statuses.append(view.effective_status)
                if "RECONCILIATION_STALE" in view.warnings:
                    stale_count += 1
                if view.effective_source is EffectivePositionSource.MANUAL:
                    if view.effective_position is None:
                        unassigned_manual += 1
                    else:
                        assigned_manual += 1
                elif view.effective_position is not None:
                    assigned_automatic += 1
                else:
                    unassigned_automatic += 1
        else:
            for row in assignments:
                status_value = (
                    row.assignment_status.value
                    if isinstance(row.assignment_status, AssignmentStatus)
                    else str(row.assignment_status)
                )
                statuses.append(status_value)
                if status_value == AssignmentStatus.ASSIGNED_AUTOMATIC.value:
                    assigned_automatic += 1
                elif status_value.startswith("UNASSIGNED"):
                    unassigned_automatic += 1

        assigned = assigned_automatic + assigned_manual
        unassigned = unassigned_automatic + unassigned_manual
        total_results = len(result_ids) if result_ids else (assigned + unassigned)

        ambiguous = sum(1 for d in detections if is_ambiguous_detection_status(d.detection_status))
        invalid_det = sum(1 for d in detections if is_invalid_detection_status(d.detection_status))
        detections_count = len(detections)
        resolved_detections_count = sum(1 for d in detections if is_resolved_position_detection(d))

        recon_status = None
        recon_id = None
        recon_version = None
        if recon is not None:
            recon_status = (
                recon.status.value
                if isinstance(recon.status, ReconciliationStatus)
                else str(recon.status)
            )
            recon_id = recon.id
            recon_version = _recon_version_as_str(recon.reconciliation_version)
            if recon_status == ReconciliationStatus.STALE.value and stale_count == 0:
                stale_count = total_results

        has_dinamic_scanner_txt_import = False
        if self._local_csv_result_writer is not None:
            txt_aisle_ids = self._local_csv_result_writer.aisle_ids_with_ingestion_source(
                command.inventory_id,
                (command.aisle_id,),
                INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
            )
            has_dinamic_scanner_txt_import = command.aisle_id in txt_aisle_ids

        allowed = resolve_positioning_allowed_actions(
            principal=command.principal,
            processing_state=processing.state,
            can_start_new=processing.can_start_new,
            recoverable=processing.recoverable,
            has_result_job=bool(result_job_id),
            operational_ux_enabled=self._operational_ux_enabled,
            reprocessing_enabled=self._reprocessing_enabled,
            recovery_enabled=self._recovery_enabled,
            overrides_enabled=self._overrides_enabled,
            reconciliation_status=recon_status,
            block_processing_start=has_dinamic_scanner_txt_import,
        )
        allowed_names = frozenset(name for name, enabled in allowed.as_dict().items() if enabled)

        warnings = build_operational_warnings(
            processing_state=processing.state,
            recoverable=processing.recoverable,
            reconciliation_status=recon_status,
            unassigned_count=unassigned,
            ambiguous_count=ambiguous,
            resolved_detections_count=resolved_detections_count,
            unordered_count=unordered,
            invalid_count=invalid_det,
            stale_count=stale_count,
            allowed_action_names=allowed_names,
        )

        supported_modes: list[str] = []
        if self._reprocessing_enabled:
            if allowed.reprocess:
                supported_modes.append(PositioningReprocessMode.REPROCESS_FULL_AISLE.value)
            if allowed.reconcile_only:
                supported_modes.append(PositioningReprocessMode.RECONCILE_ONLY.value)

        logger.info(
            "positioning_operational_view inventory_id=%s aisle_id=%s state=%s "
            "result_job_id=%s total=%s assigned=%s unassigned=%s detections=%s resolved=%s",
            command.inventory_id,
            command.aisle_id,
            processing.state,
            result_job_id,
            total_results,
            assigned,
            unassigned,
            detections_count,
            resolved_detections_count,
        )

        return AisleOperationalPositioningView(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            client_id=inventory.client_id,
            processing_state=processing.state,
            active_job_id=processing.job_id if not processing.can_start_new else None,
            result_job_id=result_job_id,
            reconciliation_status=recon_status,
            reconciliation_id=recon_id,
            reconciliation_version=recon_version,
            total_results=total_results,
            assigned_results=assigned,
            unassigned_results=unassigned,
            assigned_automatic=assigned_automatic,
            assigned_manual=assigned_manual,
            unassigned_automatic=unassigned_automatic,
            unassigned_manual=unassigned_manual,
            manual_overrides_count=manual_count,
            invalid_positions_count=invalid_det,
            stale_results_count=stale_count,
            unordered_assets_count=unordered,
            ambiguous_detections_count=ambiguous,
            detections_count=detections_count,
            recoverable=processing.recoverable,
            can_process=allowed.process,
            can_reprocess=allowed.reprocess,
            can_recover=allowed.recover,
            can_review=allowed.review,
            can_correct=allowed.correct_position,
            allowed_actions=allowed,
            warnings=warnings,
            unassigned_by_cause=unassigned_buckets_from_assignments(statuses),
            supported_reprocess_modes=tuple(supported_modes),
            last_updated_at=processing.updated_at,
            feature_flags={
                "POSITION_OPERATIONAL_UX_ENABLED": self._operational_ux_enabled,
                "POSITION_REPROCESSING_ENABLED": self._reprocessing_enabled,
                "POSITION_PROCESSING_RECOVERY_ENABLED": self._recovery_enabled,
                "POSITION_MANUAL_OVERRIDES_ENABLED": self._overrides_enabled,
            },
            has_dinamic_scanner_txt_import=has_dinamic_scanner_txt_import,
        )
