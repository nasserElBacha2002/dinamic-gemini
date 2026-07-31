"""Port for image position label detections (Phase 3)."""

from __future__ import annotations

from typing import Protocol, Sequence

from src.domain.position_label_detection.entities import ImagePositionLabelDetection


class ImagePositionLabelDetectionRepository(Protocol):
    def upsert_idempotent(self, detection: ImagePositionLabelDetection) -> ImagePositionLabelDetection:
        """Insert or update by (source_asset_id, detector_version, raw_payload_hash)."""
        ...

    def list_by_job(self, job_id: str) -> Sequence[ImagePositionLabelDetection]: ...

    def list_by_asset(
        self, job_id: str, source_asset_id: str
    ) -> Sequence[ImagePositionLabelDetection]: ...
