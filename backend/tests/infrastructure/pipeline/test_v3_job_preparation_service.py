"""Unit tests for :class:`V3JobPreparationService` (Phase 6 Step 2)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.ports.repositories import (
    AisleRepository,
    JobRepository,
    SourceAssetRepository,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_preparation_service import V3JobPreparationService
from tests.infrastructure.pipeline.test_v3_job_executor_phase5 import (
    FixedClock,
    InMemoryAisleRepo,
    InMemoryJobRepo,
    NoopRepo,
)


class _OnePhotoRepo:
    def __init__(self, aisle_id: str, now: datetime) -> None:
        self._aisle_id = aisle_id
        self._now = now

    def list_by_aisle(self, aid: str) -> Sequence[SourceAsset]:
        if aid != self._aisle_id:
            return []
        return [
            SourceAsset(
                id="asset-1",
                aisle_id=self._aisle_id,
                type=SourceAssetType.PHOTO,
                original_filename="photo.jpg",
                storage_path="a1/photo.jpg",
                mime_type="image/jpeg",
                uploaded_at=self._now,
            )
        ]


def _build_service(
    *,
    job_repo: JobRepository | None = None,
    aisle_repo: AisleRepository | None = None,
    source_asset_repo: SourceAssetRepository | None = None,
    now: datetime | None = None,
) -> tuple[V3JobPreparationService, MagicMock, JobRepository, str, str]:
    ts = now or datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "prep-job"
    aisle_id = "aisle-1"
    jobs = job_repo if job_repo is not None else InMemoryJobRepo()
    aisles = aisle_repo if aisle_repo is not None else InMemoryAisleRepo()
    assets = source_asset_repo if source_asset_repo is not None else _OnePhotoRepo(aisle_id, ts)
    state = MagicMock()
    service = V3JobPreparationService(
        job_repo=jobs,
        aisle_repo=aisles,
        source_asset_repo=assets,
        state_service=state,
        clock=FixedClock(ts),
    )
    return service, state, jobs, job_id, aisle_id


def _seed_starting_job(
    job_repo: InMemoryJobRepo,
    aisle_repo: InMemoryAisleRepo,
    *,
    job_id: str,
    aisle_id: str,
    now: datetime,
    status: JobStatus = JobStatus.STARTING,
) -> None:
    job_repo.save(
        Job(
            id=job_id,
            target_type="aisle",
            target_id=aisle_id,
            job_type="process_aisle",
            status=status,
            payload_json={"aisle_id": aisle_id},
            created_at=now,
            updated_at=now,
            execution_id="ex-prep",
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id="inv-1",
            code="A01",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )


def test_prepare_returns_halt_false_for_non_process_aisle_job() -> None:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id="legacy",
            target_type="aisle",
            target_id="a1",
            job_type="legacy_type",
            status=JobStatus.STARTING,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    service, state, _, _, _ = _build_service(job_repo=job_repo, now=now)

    result = service.prepare("legacy")

    assert result.stop is True
    assert result.return_value is False
    assert result.prepared is None
    state.mark_running.assert_not_called()


def test_prepare_returns_halt_true_for_running_reentry() -> None:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    aisle_repo = InMemoryAisleRepo()
    _seed_starting_job(
        job_repo,
        aisle_repo,
        job_id="running",
        aisle_id="aisle-1",
        now=now,
        status=JobStatus.RUNNING,
    )
    service, state, _, _, _ = _build_service(
        job_repo=job_repo, aisle_repo=aisle_repo, now=now
    )

    result = service.prepare("running")

    assert result.stop is True
    assert result.return_value is True
    state.mark_running.assert_not_called()


def test_prepare_marks_running_once_for_valid_starting_job() -> None:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    aisle_repo = InMemoryAisleRepo()
    job_id = "ok"
    aisle_id = "aisle-1"
    _seed_starting_job(job_repo, aisle_repo, job_id=job_id, aisle_id=aisle_id, now=now)
    service, state, _, _, _ = _build_service(
        job_repo=job_repo, aisle_repo=aisle_repo, now=now
    )

    result = service.prepare(job_id)

    assert result.stop is False
    assert result.prepared is not None
    assert result.prepared.job.id == job_id
    assert result.prepared.aisle_id == aisle_id
    assert len(result.prepared.assets) == 1
    state.mark_running.assert_called_once()


def test_prepare_fails_when_no_source_assets() -> None:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    aisle_repo = InMemoryAisleRepo()
    job_id = "no-assets"
    _seed_starting_job(job_repo, aisle_repo, job_id=job_id, aisle_id="aisle-1", now=now)
    service, state, _, _, _ = _build_service(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=NoopRepo(),
        now=now,
    )

    result = service.prepare(job_id)

    assert result.stop is True
    assert result.return_value is True
    state.fail_job_and_aisle.assert_called_once()
    state.mark_running.assert_not_called()


def test_prepare_returns_halt_false_when_job_does_not_exist() -> None:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    service, state, _, _, _ = _build_service(now=now)

    result = service.prepare("missing-job")

    assert result.stop is True
    assert result.return_value is False
    assert result.prepared is None
    state.mark_running.assert_not_called()
    state.fail_job.assert_not_called()


def test_prepare_fails_when_payload_missing_aisle_id() -> None:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id="no-aisle-id",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    service, state, _, _, _ = _build_service(job_repo=job_repo, now=now)

    result = service.prepare("no-aisle-id")

    assert result.stop is True
    assert result.return_value is True
    state.fail_job.assert_called_once_with("no-aisle-id", "Missing aisle_id in payload")
    state.mark_running.assert_not_called()


def test_prepare_fails_when_aisle_does_not_exist() -> None:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id="missing-aisle",
            target_type="aisle",
            target_id="aisle-missing",
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json={"aisle_id": "aisle-missing"},
            created_at=now,
            updated_at=now,
        )
    )
    service, state, _, _, _ = _build_service(job_repo=job_repo, now=now)

    result = service.prepare("missing-aisle")

    assert result.stop is True
    assert result.return_value is True
    state.fail_job.assert_called_once_with("missing-aisle", "Aisle not found: aisle-missing")
    state.mark_running.assert_not_called()


def test_prepare_skips_already_canceled_job() -> None:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    aisle_repo = InMemoryAisleRepo()
    _seed_starting_job(
        job_repo,
        aisle_repo,
        job_id="canceled",
        aisle_id="aisle-1",
        now=now,
        status=JobStatus.CANCELED,
    )
    service, state, _, _, _ = _build_service(
        job_repo=job_repo, aisle_repo=aisle_repo, now=now
    )

    result = service.prepare("canceled")

    assert result.stop is True
    assert result.return_value is True
    state.mark_running.assert_not_called()
    state.cancel_job.assert_not_called()


def test_prepare_cancel_requested_before_execution_calls_cancel_job() -> None:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    aisle_repo = InMemoryAisleRepo()
    _seed_starting_job(
        job_repo,
        aisle_repo,
        job_id="cancel-before",
        aisle_id="aisle-1",
        now=now,
        status=JobStatus.CANCEL_REQUESTED,
    )
    service, state, _, _, _ = _build_service(
        job_repo=job_repo, aisle_repo=aisle_repo, now=now
    )

    result = service.prepare("cancel-before")

    assert result.stop is True
    assert result.return_value is True
    state.cancel_job.assert_called_once()
    state.mark_running.assert_not_called()
