"""In-memory repository for unit tests."""

from __future__ import annotations

from datetime import datetime

from src.application.ports.mobile_preliminary_detection_repository import (
    PreliminaryUniqueViolationError,
)
from src.domain.mobile_preliminary_detections.entities import MobilePreliminaryDetection


class MemoryMobilePreliminaryDetectionRepository:
    def __init__(self) -> None:
        self._by_draft: dict[str, MobilePreliminaryDetection] = {}
        self._by_idem: dict[tuple[str, str, str, str], MobilePreliminaryDetection] = {}

    def get_by_draft_id(self, draft_id: str) -> MobilePreliminaryDetection | None:
        return self._by_draft.get((draft_id or "").strip())

    def get_by_idempotency_key(
        self,
        *,
        client_file_id: str,
        detector_version: str,
        parser_version: str,
        prepared_asset_sha256: str,
    ) -> MobilePreliminaryDetection | None:
        key = (
            (client_file_id or "").strip(),
            (detector_version or "").strip(),
            (parser_version or "").strip(),
            (prepared_asset_sha256 or "").strip(),
        )
        return self._by_idem.get(key)

    def insert(self, row: MobilePreliminaryDetection) -> MobilePreliminaryDetection:
        if row.draft_id in self._by_draft:
            raise PreliminaryUniqueViolationError("draft_id")
        key = (
            row.client_file_id,
            row.detector_version,
            row.parser_version,
            row.prepared_asset_sha256,
        )
        if key in self._by_idem:
            raise PreliminaryUniqueViolationError("idempotency_key")
        self._by_draft[row.draft_id] = row
        self._by_idem[key] = row
        return row

    def delete_expired(self, *, now: datetime, limit: int = 500) -> int:
        expired = [r for r in self._by_draft.values() if r.expires_at <= now][:limit]
        for row in expired:
            self._by_draft.pop(row.draft_id, None)
            self._by_idem.pop(
                (
                    row.client_file_id,
                    row.detector_version,
                    row.parser_version,
                    row.prepared_asset_sha256,
                ),
                None,
            )
        return len(expired)
