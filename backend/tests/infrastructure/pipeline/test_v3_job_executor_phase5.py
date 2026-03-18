"""Tests for V3JobExecutor Phase 5 — job-level visual reference metadata persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Sequence
from unittest.mock import MagicMock, patch

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    InventoryRepository,
    InventoryVisualReferenceRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    SourceAssetRepository,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_executor import RUN_ID, V3JobExecutor
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult
from src.pipeline.run_metadata import (
    RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT,
    default_empty_block,
)


class InMemoryJobRepo(JobRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Job] = {}

    def save(self, job: Job) -> None:
        self._store[job.id] = job

    def get_by_id(self, job_id: str) -> Optional[Job]:
        return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Optional[Job]:
        return None

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> Dict[str, Job]:
        return {}


class InMemoryAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        return None


class NoopRepo(
    EvidenceRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    SourceAssetRepository,
    InventoryRepository,
    InventoryVisualReferenceRepository,
):
    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        pass

    def get_by_id(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    def list_by_aisle(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def list_by_aisle_query(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def list_by_aisles(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def list_by_position(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def list_by_entity(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def save_many(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        pass

    def list_for_scope(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def replace_for_scope(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        pass

    def list_by_inventory(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def list_all(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def create(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        pass

    def create_many(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        pass


class FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def test_mark_success_without_run_metadata_preserves_report_path_only() -> None:
    """Backward compatibility: _mark_success without run_metadata sets report_path and default empty visual_reference_context."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job = Job(
        id="j1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)
    noop = NoopRepo()

    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=noop,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=noop,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )
    report_path = Path("/tmp/run/hybrid_report.json")
    executor._mark_success("j1", aisle, report_path, now, run_metadata=None)

    updated = job_repo.get_by_id("j1")
    assert updated is not None
    assert updated.result_json["report_path"] == str(report_path)
    assert updated.result_json.get(RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT) == default_empty_block()


def test_mark_success_with_run_metadata_merges_into_result_json() -> None:
    """When run_metadata is provided, it is merged into job.result_json."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job = Job(
        id="j2",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)
    noop = NoopRepo()

    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=noop,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=noop,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )

    run_metadata = {
        RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT: {
            "resolved": True,
            "reference_ids": ["ref-1", "ref-2"],
            "resolved_count": 2,
            "provider_consumed": True,
            "provider_consumed_count": 2,
        },
    }
    report_path = Path("/tmp/run/hybrid_report.json")
    executor._mark_success("j2", aisle, report_path, now, run_metadata=run_metadata)

    updated = job_repo.get_by_id("j2")
    assert updated is not None
    assert updated.result_json is not None
    assert updated.result_json["report_path"] == str(report_path)
    vrc = updated.result_json.get(RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT)
    assert vrc is not None
    assert vrc["resolved"] is True
    assert vrc["reference_ids"] == ["ref-1", "ref-2"]
    assert vrc["resolved_count"] == 2
    assert vrc["provider_consumed"] is True
    assert vrc["provider_consumed_count"] == 2


def test_persist_failure_sets_error_message_with_persist_prefix() -> None:
    """Phase 4: When persist use case raises, job and aisle fail with error_message starting with 'Persist: '."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "j-persist-fail"
    aisle_id = "aisle-1"
    job_repo = InMemoryJobRepo()
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.QUEUED,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)

    class AssetRepoWithOnePhoto:
        def list_by_aisle(self, aid: str):
            if aid != aisle_id:
                return []
            return [
                SourceAsset(
                    id="asset-1",
                    aisle_id=aisle_id,
                    type=SourceAssetType.PHOTO,
                    original_filename="photo.jpg",
                    storage_path="a1/photo.jpg",
                    mime_type="image/jpeg",
                    uploaded_at=now,
                )
            ]

    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=AssetRepoWithOnePhoto(),
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=noop,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )

    with patch.object(
        executor, "_persist_use_case", MagicMock(side_effect=ValueError("simulated persist error"))
    ):
        # We never reach persist without running pipeline; patch pipeline to succeed and create report
        base_path = Path("/tmp/test_persist_fail")
        base_path.mkdir(parents=True, exist_ok=True)
        (base_path / job_id).mkdir(parents=True, exist_ok=True)
        run_dir = base_path / job_id / RUN_ID
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "hybrid_report.json").write_text(json.dumps({"entities": []}), encoding="utf-8")
        v3_base = base_path / "v3_uploads"
        v3_base.mkdir(parents=True, exist_ok=True)
        (v3_base / "a1").mkdir(parents=True, exist_ok=True)
        (v3_base / "a1" / "photo.jpg").write_bytes(b"fake")

        with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as mock_settings:
            mock_settings.return_value.output_dir = str(base_path)
            with patch(
                "src.infrastructure.pipeline.v3_job_executor.HybridInventoryPipeline"
            ) as mock_pipeline_cls:
                mock_pipeline_cls.return_value.process_video.return_value = PipelineRunResult(
                    exit_code=0, run_metadata=None
                )
                executor.execute(base_path, job_id)

    # Assert the dedicated persist-failure path was taken (stage-prefixed message), not the generic handler.
    updated_job = job_repo.get_by_id(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.FAILED
    assert updated_job.error_message is not None
    assert updated_job.error_message.startswith("Persist:"), (
        "Phase 4: persist failures must prefix error_message with 'Persist: ' for diagnosability"
    )
    assert "simulated persist error" in updated_job.error_message
