"""In-memory ImagePositionLabelDetectionRepository."""

from __future__ import annotations

from src.domain.position_label_detection.entities import ImagePositionLabelDetection


def _idem_key(d: ImagePositionLabelDetection) -> tuple[str, str, str]:
    return (
        d.source_asset_id,
        d.detector_version,
        (d.raw_payload_hash or "") + ":" + d.detection_status.value,
    )


class MemoryImagePositionLabelDetectionRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, ImagePositionLabelDetection] = {}
        self._by_idem: dict[tuple[str, str, str], str] = {}

    def upsert_idempotent(self, detection: ImagePositionLabelDetection) -> ImagePositionLabelDetection:
        key = _idem_key(detection)
        existing_id = self._by_idem.get(key)
        if existing_id and existing_id in self._by_id:
            prev = self._by_id[existing_id]
            detection.id = prev.id
            detection.created_at = prev.created_at
        self._by_id[detection.id] = detection
        self._by_idem[key] = detection.id
        return detection

    def list_by_job(self, job_id: str) -> list[ImagePositionLabelDetection]:
        rows = [d for d in self._by_id.values() if d.job_id == job_id]
        rows.sort(key=lambda d: (d.sequence_number or 0, d.created_at.isoformat(), d.id))
        return rows

    def list_by_asset(
        self, job_id: str, source_asset_id: str
    ) -> list[ImagePositionLabelDetection]:
        return [
            d
            for d in self.list_by_job(job_id)
            if d.source_asset_id == source_asset_id
        ]
