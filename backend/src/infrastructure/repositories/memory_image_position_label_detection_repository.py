"""In-memory ImagePositionLabelDetectionRepository."""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.position_label_detection.entities import ImagePositionLabelDetection


def _idem_key(d: ImagePositionLabelDetection) -> tuple[str, str, str, str]:
    return (
        d.job_id,
        d.source_asset_id,
        d.detector_version,
        (d.raw_payload_hash or "") + ":" + d.detection_status.value,
    )


class MemoryImagePositionLabelDetectionRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, ImagePositionLabelDetection] = {}
        self._by_idem: dict[tuple[str, str, str, str], str] = {}

    def upsert_idempotent(self, detection: ImagePositionLabelDetection) -> ImagePositionLabelDetection:
        hash_key = (detection.raw_payload_hash or "").strip() or (
            f"status:{detection.detection_status.value}"
        )
        detection.raw_payload_hash = hash_key
        key = _idem_key(detection)
        existing_id = self._by_idem.get(key)
        if existing_id and existing_id in self._by_id:
            prev = self._by_id[existing_id]
            # Preserve identity scope — never rewrite job/inventory/client/asset.
            detection.id = prev.id
            detection.created_at = prev.created_at
            detection.job_id = prev.job_id
            detection.inventory_id = prev.inventory_id
            detection.client_id = prev.client_id
            detection.source_asset_id = prev.source_asset_id
        self._by_id[detection.id] = detection
        self._by_idem[key] = detection.id
        return detection

    def replace_asset_detections_atomically(
        self,
        *,
        job_id: str,
        source_asset_id: str,
        detector_version: str,
        detections: Sequence[ImagePositionLabelDetection],
    ) -> list[ImagePositionLabelDetection]:
        out: list[ImagePositionLabelDetection] = []
        kept_ids: set[str] = set()
        for detection in detections:
            saved = self.upsert_idempotent(detection)
            out.append(saved)
            kept_ids.add(saved.id)
        to_remove = [
            d.id
            for d in self._by_id.values()
            if d.job_id == job_id
            and d.source_asset_id == source_asset_id
            and d.detector_version == detector_version
            and d.id not in kept_ids
        ]
        for rid in to_remove:
            old = self._by_id.pop(rid, None)
            if old is None:
                continue
            self._by_idem.pop(_idem_key(old), None)
        return out

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
