"""Port for mobile preliminary detection persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

from src.domain.mobile_preliminary_detections.entities import MobilePreliminaryDetection


class PreliminaryUniqueViolationError(Exception):
    """Raised when INSERT hits UNIQUE(draft_id) or UNIQUE(client+versions+hash)."""

    def __init__(self, constraint: str) -> None:
        self.constraint = constraint  # "draft_id" | "idempotency_key"
        super().__init__(constraint)


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

    def insert(self, row: MobilePreliminaryDetection) -> MobilePreliminaryDetection:
        """Insert a new row. Raises PreliminaryUniqueViolationError on unique race."""
        ...

    def delete_expired(self, *, now: datetime, limit: int = 500) -> int: ...

    def list_validated_by_aisle(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        limit: int = 500,
    ) -> Sequence[MobilePreliminaryDetection]: ...

    def list_validated_by_asset_ids(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        asset_ids: Sequence[str],
        limit: int = 500,
    ) -> Sequence[MobilePreliminaryDetection]: ...
