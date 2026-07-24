"""Port for mobile preliminary detection persistence."""

from __future__ import annotations

from typing import Protocol

from src.domain.mobile_preliminary_detections.entities import MobilePreliminaryDetection


class MobilePreliminaryDetectionRepository(Protocol):
    def get_by_draft_id(self, draft_id: str) -> MobilePreliminaryDetection | None: ...

    def get_by_idempotency_key(
        self,
        *,
        client_file_id: str,
        detector_version: str,
        parser_version: str,
        prepared_asset_sha256: str,
    ) -> MobilePreliminaryDetection | None: ...

    def upsert(self, row: MobilePreliminaryDetection) -> MobilePreliminaryDetection: ...
