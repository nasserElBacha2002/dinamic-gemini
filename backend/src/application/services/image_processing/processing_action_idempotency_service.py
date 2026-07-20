"""Durable idempotency helper for Phase 7 processing mutations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from src.application.errors import IdempotencyKeyReusedError
from src.application.ports.processing_action_idempotency_repository import (
    ProcessingActionIdempotencyRepository,
)
from src.domain.image_processing.processing_action_idempotency import (
    ProcessingActionIdempotencyRecord,
)


def hash_request_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class IdempotencyBeginResult:
    replay: bool
    record: ProcessingActionIdempotencyRecord | None
    response: dict[str, Any] | None = None


class ProcessingActionIdempotencyService:
    def __init__(self, repo: ProcessingActionIdempotencyRepository) -> None:
        self._repo = repo

    def begin(
        self,
        *,
        action_type: str,
        job_id: str,
        asset_id: str,
        idempotency_key: str | None,
        payload: dict[str, Any],
        actor: str | None,
        now: datetime,
    ) -> IdempotencyBeginResult:
        if not idempotency_key:
            return IdempotencyBeginResult(replay=False, record=None)
        request_hash = hash_request_payload(payload)
        existing = self._repo.get(
            action_type=action_type,
            job_id=job_id,
            asset_id=asset_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise IdempotencyKeyReusedError(
                    "IDEMPOTENCY_KEY_REUSED: same key with different payload"
                )
            return IdempotencyBeginResult(
                replay=True,
                record=existing,
                response=dict(existing.response_json or {}),
            )
        record = ProcessingActionIdempotencyRecord(
            id=str(uuid4()),
            action_type=action_type,
            job_id=job_id,
            asset_id=asset_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_json={},
            status="IN_PROGRESS",
            created_at=now,
            updated_at=now,
            actor=actor,
        )
        try:
            self._repo.insert(record)
        except IdempotencyKeyReusedError:
            # Concurrent insert won — re-read and treat as replay or conflict.
            existing = self._repo.get(
                action_type=action_type,
                job_id=job_id,
                asset_id=asset_id,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise
            if existing.request_hash != request_hash:
                raise IdempotencyKeyReusedError(
                    "IDEMPOTENCY_KEY_REUSED: same key with different payload"
                )
            return IdempotencyBeginResult(
                replay=True,
                record=existing,
                response=dict(existing.response_json or {}),
            )
        return IdempotencyBeginResult(replay=False, record=record)

    def complete(
        self,
        record: ProcessingActionIdempotencyRecord | None,
        *,
        response: dict[str, Any],
        status: str = "COMPLETED",
        state_version: int | None = None,
        now: datetime,
    ) -> None:
        if record is None:
            return
        record.response_json = response
        record.status = status
        record.state_version = state_version
        record.updated_at = now
        self._repo.update_response(record)


__all__ = [
    "IdempotencyBeginResult",
    "ProcessingActionIdempotencyService",
    "hash_request_payload",
]
