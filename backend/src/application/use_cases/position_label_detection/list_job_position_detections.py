"""List position-label detections for a job / asset (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.image_position_label_detection_repository import (
    ImagePositionLabelDetectionRepository,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.domain.position_label_detection.entities import ImagePositionLabelDetection


@dataclass(frozen=True)
class ListJobPositionDetectionsCommand:
    inventory_id: str
    job_id: str
    principal: AccessPrincipal
    source_asset_id: str | None = None


class ListJobPositionDetectionsUseCase:
    def __init__(
        self,
        *,
        detection_repo: ImagePositionLabelDetectionRepository,
        inventory_repo: InventoryRepository,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._detections = detection_repo
        self._inventories = inventory_repo
        self._jobs = job_repo
        self._aisles = aisle_repo
        self._access = access_policy

    def execute(
        self, command: ListJobPositionDetectionsCommand
    ) -> list[ImagePositionLabelDetection]:
        self._access.require_inventory(command.inventory_id, command.principal)
        job = self._jobs.get_by_id(command.job_id)
        if job is None:
            return []
        if job.target_type != "aisle":
            return []
        aisle = self._aisles.get_by_id(job.target_id)
        if aisle is None or aisle.inventory_id != command.inventory_id:
            return []
        if command.source_asset_id:
            return list(
                self._detections.list_by_asset(command.job_id, command.source_asset_id)
            )
        return list(self._detections.list_by_job(command.job_id))
