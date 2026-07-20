"""Port — durable processing action idempotency."""

from __future__ import annotations

from typing import Protocol

from src.domain.image_processing.processing_action_idempotency import (
    ProcessingActionIdempotencyRecord,
)


class ProcessingActionIdempotencyRepository(Protocol):
    def get(
        self,
        *,
        action_type: str,
        job_id: str,
        asset_id: str,
        idempotency_key: str,
    ) -> ProcessingActionIdempotencyRecord | None: ...

    def insert(self, record: ProcessingActionIdempotencyRecord) -> None:
        """Insert; raise conflict on unique violation."""
        ...

    def update_response(self, record: ProcessingActionIdempotencyRecord) -> None: ...
