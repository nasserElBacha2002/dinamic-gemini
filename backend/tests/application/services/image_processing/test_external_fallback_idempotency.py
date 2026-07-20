"""Idempotency / recovery contract tests for external image analysis requests (memory)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.domain.image_processing.external_image_analysis_request import (
    ExternalImageAnalysisRequest,
    ExternalRequestStatus,
    build_external_idempotency_key,
)
from src.infrastructure.repositories.memory_external_image_analysis_request_repository import (
    MemoryExternalImageAnalysisRequestRepository,
)


def test_try_claim_is_idempotent_same_key() -> None:
    repo = MemoryExternalImageAnalysisRequestRepository()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    key = build_external_idempotency_key(
        job_id="j1",
        asset_id="a1",
        provider="gemini",
        model="m",
        prompt_version="1",
        configuration_snapshot_version=1,
    )
    first = ExternalImageAnalysisRequest(
        id=str(uuid4()),
        idempotency_key=key,
        job_id="j1",
        asset_id="a1",
        provider="gemini",
        model="m",
        prompt_key="k",
        prompt_version="1",
        configuration_snapshot_version=1,
        status=ExternalRequestStatus.CLAIMED,
        created_at=now,
        updated_at=now,
    )
    claimed = repo.try_claim(request=first)
    assert claimed.id == first.id
    second = ExternalImageAnalysisRequest(
        id=str(uuid4()),
        idempotency_key=key,
        job_id="j1",
        asset_id="a1",
        provider="gemini",
        model="m",
        prompt_key="k",
        prompt_version="1",
        configuration_snapshot_version=1,
        status=ExternalRequestStatus.CLAIMED,
        created_at=now,
        updated_at=now,
    )
    again = repo.try_claim(request=second)
    assert again.id == first.id
    assert again.id != second.id


def test_distinct_assets_get_distinct_keys() -> None:
    k1 = build_external_idempotency_key(
        job_id="j1",
        asset_id="a1",
        provider="gemini",
        model="m",
        prompt_version="1",
        configuration_snapshot_version=1,
    )
    k2 = build_external_idempotency_key(
        job_id="j1",
        asset_id="a2",
        provider="gemini",
        model="m",
        prompt_version="1",
        configuration_snapshot_version=1,
    )
    assert k1 != k2
