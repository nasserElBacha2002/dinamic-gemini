"""In-memory repository for unit tests."""

from __future__ import annotations

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

    def upsert(self, row: MobilePreliminaryDetection) -> MobilePreliminaryDetection:
        self._by_draft[row.draft_id] = row
        self._by_idem[
            (
                row.client_file_id,
                row.detector_version,
                row.parser_version,
                row.prepared_asset_sha256,
            )
        ] = row
        return row
