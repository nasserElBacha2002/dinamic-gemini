"""Durable GLOBAL_BATCH request journal (one row per batch fingerprint)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class GlobalFallbackBatchStatus(str, Enum):
    PREPARED = "PREPARED"
    CALLING = "CALLING"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    VALIDATED = "VALIDATED"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"


@dataclass
class GlobalFallbackBatchRequest:
    """Durable physical batch for GLOBAL_BATCH external fallback."""

    id: str
    job_id: str
    execution_id: str
    attempt: int
    batch_index: int
    batch_count: int
    batch_fingerprint: str
    status: GlobalFallbackBatchStatus
    ordered_asset_ids: list[str]
    provider: str
    model: str | None
    schema_version: str
    configuration_fingerprint: str
    prompt_fingerprint: str
    prepared_image_hashes: list[str]
    created_at: datetime
    updated_at: datetime
    provider_request_id: str | None = None
    response_sha256: str | None = None
    normalized_response_json: dict[str, Any] | None = None
    frame_to_asset_map: dict[str, str] = field(default_factory=dict)
    merge_plan_json: dict[str, Any] | None = None
    applied_operation_keys: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    worker_token: str | None = None
    estimated_cost: float | None = None
    prompt_tokens: int | None = None
    response_tokens: int | None = None
    duration_ms: int | None = None


def sanitize_entities_for_storage(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Allowlist entity fields for durable storage (no free-form provider dumps)."""
    allow = {
        "internal_code",
        "quantity",
        "confidence",
        "source_image_id",
        "source_asset_id",
        "warnings",
        "entity_uid",
        "product_label_quantity",
    }
    out: list[dict[str, Any]] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        out.append({k: ent[k] for k in allow if k in ent})
    return out
