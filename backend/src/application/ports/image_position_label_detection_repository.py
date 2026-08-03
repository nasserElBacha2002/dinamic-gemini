"""Port for image position label detections (Phase 3)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.domain.position_label_detection.entities import ImagePositionLabelDetection


class ImagePositionLabelDetectionRepository(Protocol):
    def upsert_idempotent(self, detection: ImagePositionLabelDetection) -> ImagePositionLabelDetection:
        """Insert or update by job-scoped identity (does not move rows across jobs)."""
        ...

    def replace_asset_detections_atomically(
        self,
        *,
        job_id: str,
        source_asset_id: str,
        detector_version: str,
        detections: Sequence[ImagePositionLabelDetection],
    ) -> list[ImagePositionLabelDetection]:
        """Replace all detections for one job/asset/detector revision in one transaction."""
        ...

    def list_by_job(self, job_id: str) -> Sequence[ImagePositionLabelDetection]: ...

    def list_by_asset(
        self, job_id: str, source_asset_id: str
    ) -> Sequence[ImagePositionLabelDetection]: ...
