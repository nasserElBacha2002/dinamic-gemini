"""Get ordered positioning sequence frames for an aisle/job (Phase 7 corrections)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import AisleNotFoundError, JobNotFoundError
from src.application.ports.client_position_label_repository import (
    ClientPositionLabelRepository,
)
from src.application.ports.image_position_label_detection_repository import (
    ImagePositionLabelDetectionRepository,
)
from src.application.ports.job_image_coverage_repository import JobImageCoverageRepository
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.manual_position_override_repository import (
    ManualPositionOverrideRepository,
)
from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
)
from src.application.ports.repositories import (
    AisleRepository,
    JobRepository,
    ProductRecordRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
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
from src.application.services.positioning_operational.warnings_builder import (
    transition_message_for_action,
)
from src.domain.position_overrides.entities import EffectivePositionSource
from src.domain.position_reconciliation.entities import AssignmentStatus
from src.domain.positioning_operational.entities import PositioningSequenceFrame


@dataclass(frozen=True)
class GetAislePositioningSequenceCommand:
    inventory_id: str
    aisle_id: str
    principal: AccessPrincipal
    job_id: str
    page: int = 1
    page_size: int = 50


@dataclass(frozen=True)
class GetAislePositioningSequenceResult:
    job_id: str
    items: tuple[PositioningSequenceFrame, ...]
    total: int
    page: int
    page_size: int


class GetAislePositioningSequenceUseCase:
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        access_policy: InventoryAccessPolicy,
        reconciliation_repo: PositionReconciliationRepository,
        detection_repo: ImagePositionLabelDetectionRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        override_repo: ManualPositionOverrideRepository | None,
        label_repo: ClientPositionLabelRepository | None,
        coverage_repo: JobImageCoverageRepository,
        product_record_repo: ProductRecordRepository,
        enrichment_enabled: bool = True,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._access = access_policy
        self._reconciliation_repo = reconciliation_repo
        self._detection_repo = detection_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._override_repo = override_repo
        self._label_repo = label_repo
        self._final_results = JobFinalItemResultReader(
            coverage_repo=coverage_repo,
            product_record_repo=product_record_repo,
        )
        self._enrichment_enabled = enrichment_enabled

    def execute(
        self, command: GetAislePositioningSequenceCommand
    ) -> GetAislePositioningSequenceResult:
        self._access.require_inventory(command.inventory_id, command.principal)
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )
        job = self._job_repo.get_by_id(command.job_id)
        if job is None:
            raise JobNotFoundError(command.job_id)
        if job.target_type != "aisle" or job.target_id != command.aisle_id:
            raise AisleNotFoundError(command.aisle_id)

        links = sorted(
            self._job_source_asset_repo.list_for_job(command.job_id),
            key=lambda link: (
                link.sequence_number
                if link.sequence_number is not None
                else link.position_order,
                link.source_asset_id,
            ),
        )
        page = max(1, int(command.page or 1))
        page_size = max(1, min(int(command.page_size or 50), 200))
        total = len(links)
        start = (page - 1) * page_size
        end = start + page_size
        page_links = links[start:end]
        page_asset_ids = [link.source_asset_id for link in page_links]

        detections = list(self._detection_repo.list_by_job(command.job_id))
        det_by_asset: dict[str, list] = defaultdict(list)
        for d in detections:
            if d.source_asset_id in page_asset_ids:
                det_by_asset[d.source_asset_id].append(d)

        assignments = list(self._reconciliation_repo.list_active_assignments(command.job_id))
        asg_by_asset: dict[str, list] = defaultdict(list)
        for a in assignments:
            if a.source_asset_id in page_asset_ids:
                asg_by_asset[a.source_asset_id].append(a)

        finals = self._final_results.list_for_job(
            job_id=command.job_id,
            aisle_id=command.aisle_id,
            asset_ids=tuple(page_asset_ids),
        )
        finals_by_asset: dict[str, list] = defaultdict(list)
        for row in finals:
            finals_by_asset[row.source_asset_id].append(row)

        result_ids = [row.result_id for row in finals]
        for a in assignments:
            if a.source_asset_id in page_asset_ids and a.result_id not in result_ids:
                result_ids.append(a.result_id)

        effective_by_result: dict = {}
        if result_ids and self._override_repo is not None:
            effective_by_result = EffectivePositionReader(
                automatic_reader=PublishedPositionAssignmentReader(
                    reconciliation_repo=self._reconciliation_repo,
                    enrichment_enabled=self._enrichment_enabled,
                ),
                override_repo=self._override_repo,
                label_repo=self._label_repo,
            ).load_for_job(command.job_id, result_ids=result_ids)

        frames: list[PositioningSequenceFrame] = []
        for link in page_links:
            asset_id = link.source_asset_id
            asset_asg = asg_by_asset.get(asset_id, [])
            asset_det = det_by_asset.get(asset_id, [])
            asset_finals = finals_by_asset.get(asset_id, [])
            seq = link.sequence_number if link.sequence_number is not None else link.position_order
            primary_det = asset_det[0] if asset_det else None
            label_name = None
            det_status = None
            if primary_det is not None:
                det_status = str(primary_det.detection_status)
                label_name = primary_det.position_name_snapshot

            auto_summaries: list[str] = []
            transition = None
            for a in asset_asg:
                status_value = (
                    a.assignment_status.value
                    if isinstance(a.assignment_status, AssignmentStatus)
                    else str(a.assignment_status)
                )
                pos_name = a.position_name_snapshot or ""
                auto_summaries.append(f"{a.result_id[:8]}… → {pos_name or status_value}")
                if transition is None and a.assignment_reason:
                    transition = a.assignment_reason

            eff_summaries: list[str] = []
            warn: list[str] = []
            if seq is None:
                warn.append("Sin número de secuencia")
            if not asset_det and not asset_asg and not asset_finals:
                warn.append("Sin detecciones ni productos")

            for row in asset_finals:
                view = effective_by_result.get(row.result_id)
                if view is None:
                    continue
                source = view.effective_source.value
                if view.effective_position is not None:
                    eff_summaries.append(
                        f"{row.result_id[:8]}… → {view.effective_position.name or view.effective_position.id} ({source})"
                    )
                else:
                    eff_summaries.append(f"{row.result_id[:8]}… → sin posición ({source})")
                if view.effective_source is EffectivePositionSource.NONE:
                    warn.append("Producto(s) sin posición efectiva")
                for w in view.warnings:
                    warn.append(w)

            if not asset_finals and any(_is_unassigned(a) for a in asset_asg):
                warn.append("Producto(s) sin posición")

            frames.append(
                PositioningSequenceFrame(
                    sequence_number=seq,
                    source_asset_id=asset_id,
                    filename=link.original_filename,
                    position_detection_status=det_status,
                    position_label_name=label_name,
                    transition_action=str(transition) if transition else None,
                    transition_message=transition_message_for_action(
                        str(transition) if transition else det_status
                    ),
                    product_count=len(asset_finals) or len(asset_asg),
                    automatic_assignment_summaries=tuple(auto_summaries[:8]),
                    effective_assignment_summaries=tuple(eff_summaries[:8] or auto_summaries[:8]),
                    warnings=tuple(dict.fromkeys(warn)),
                )
            )

        return GetAislePositioningSequenceResult(
            job_id=command.job_id,
            items=tuple(frames),
            total=total,
            page=page,
            page_size=page_size,
        )


def _is_unassigned(assignment: object) -> bool:
    status = getattr(assignment, "assignment_status", None)
    value = status.value if isinstance(status, AssignmentStatus) else str(status or "")
    return value.startswith("UNASSIGNED")
