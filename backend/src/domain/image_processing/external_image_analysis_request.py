"""Durable external image-analysis request claim (Phase 5 corrections)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ExternalRequestStatus(str, Enum):
    CLAIMED = "CLAIMED"
    IN_FLIGHT = "IN_FLIGHT"
    PROVIDER_SUCCEEDED = "PROVIDER_SUCCEEDED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PERSISTENCE_PENDING = "PERSISTENCE_PENDING"
    PERSISTED = "PERSISTED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"


@dataclass
class ExternalImageAnalysisRequest:
    id: str
    idempotency_key: str
    job_id: str
    asset_id: str
    provider: str
    status: ExternalRequestStatus
    created_at: datetime
    updated_at: datetime
    model: str | None = None
    prompt_key: str | None = None
    prompt_version: str | None = None
    configuration_snapshot_version: int | None = None
    attempt_id: str | None = None
    worker_token: str | None = None
    request_image_sha256: str | None = None
    provider_response_sha256: str | None = None
    normalized_result_sha256: str | None = None
    normalized_result: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    estimated_cost: float | None = None
    duration_ms: int | None = None
    confidence: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    position_id: str | None = None
    active_result_id: str | None = None
    client_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def build_external_idempotency_key(
    *,
    job_id: str,
    asset_id: str,
    provider: str,
    model: str | None,
    prompt_version: str | None,
    configuration_snapshot_version: int | None,
) -> str:
    """Logical identity for one external analysis (not shared across distinct assets)."""
    return "|".join(
        [
            (job_id or "").strip(),
            (asset_id or "").strip(),
            (provider or "").strip().lower(),
            (model or "").strip().lower() or "default",
            (prompt_version or "").strip() or "none",
            str(configuration_snapshot_version if configuration_snapshot_version is not None else ""),
        ]
    )


__all__ = [
    "ExternalImageAnalysisRequest",
    "ExternalRequestStatus",
    "build_external_idempotency_key",
]
