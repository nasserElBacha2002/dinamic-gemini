"""Tests for V3JobExecutor Phase 5 — job-level visual reference metadata persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
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
from src.application.services.aisle_analysis_context_builder import AisleAnalysisContextBuilder
from src.application.services.inventory_visual_reference_resolver import InventoryVisualReferenceResolver
from src.application.use_cases.manage_inventory_visual_references import DeleteInventoryVisualReferenceUseCase
from src.application.use_cases.upload_inventory_visual_references import (
    UploadInventoryVisualReferencesUseCase,
    UploadedVisualReferenceFile,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_executor import RUN_ID, V3JobExecutor
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DURABLE_ARTIFACT_KIND_EXECUTION_LOG,
    DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON,
    worker_output_storage_keys,
)
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import AnalysisContext, VisualReferenceContext
from src.pipeline.context.run_context import RunContext
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult
from src.pipeline.run_metadata import (
    RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT,
    build_run_metadata,
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

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        return []


class CountingJobRepo(InMemoryJobRepo):
    def __init__(self) -> None:
        super().__init__()
        self.get_calls = 0

    def get_by_id(self, job_id: str) -> Optional[Job]:
        self.get_calls += 1
        return super().get_by_id(job_id)


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

    def update(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        pass

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        pass

    def summarize_assets_for_aisles(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return {}


class InMemoryInventoryRepo(InventoryRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class InMemoryVisualReferenceRepo(InventoryVisualReferenceRepository):
    def __init__(self) -> None:
        self._store: Dict[str, InventoryVisualReference] = {}

    def get_by_id(self, reference_id: str) -> Optional[InventoryVisualReference]:
        return self._store.get(reference_id)

    def create(self, reference: InventoryVisualReference) -> None:
        self._store[reference.id] = reference

    def create_many(self, references: Sequence[InventoryVisualReference]) -> None:
        for reference in references:
            self._store[reference.id] = reference

    def list_by_inventory(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        refs = [r for r in self._store.values() if r.inventory_id == inventory_id]
        refs.sort(key=lambda r: (r.created_at, r.id))
        return refs

    def update(self, reference: InventoryVisualReference) -> None:
        self._store[reference.id] = reference

    def delete(self, reference_id: str) -> None:
        self._store.pop(reference_id, None)


class StubArtifactStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def save_file(self, path: str, file_obj, content_type: str):  # type: ignore[no-untyped-def]
        return path

    def put_object(self, path: str, file_obj, content_type: str):  # type: ignore[no-untyped-def]
        payload = file_obj.read()
        return type(
            "StoredArtifactStub",
            (),
            {
                "storage_provider": "local",
                "storage_bucket": None,
                "storage_key": path,
                "content_type": content_type,
                "file_size_bytes": len(payload),
                "etag": "etag-test",
            },
        )()

    def delete_file(self, path: str) -> None:
        self.deleted.append(path)


class FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set_now(self, now: datetime) -> None:
        self._now = now


def test_mark_success_without_run_metadata_preserves_report_path_only() -> None:
    """Backward compatibility: mark_success without run_metadata sets report_path and default empty visual_reference_context."""
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
    executor._state.mark_success("j1", aisle, report_path, run_metadata=None)

    updated = job_repo.get_by_id("j1")
    assert updated is not None
    assert updated.result_json["report_path"] == str(report_path)
    assert updated.result_json.get(RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT) == default_empty_block()
    # Phase 7: provider key always present; None when run_metadata absent
    assert "provider" in updated.result_json
    assert updated.result_json["provider"] is None


def test_mark_success_clears_stale_aisle_error_fields_after_previous_failure() -> None:
    """After fail_job_and_aisle, a later successful run must not leave PROCESSING_FAILED on the aisle."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id="j-retry-ok",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
        )
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.FAILED,
        created_at=now,
        updated_at=now,
        error_code="PROCESSING_FAILED",
        error_message="previous pipeline error",
        retryable=True,
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
    executor._state.mark_success("j-retry-ok", aisle, Path("/tmp/run/hybrid_report.json"), run_metadata=None)
    updated_aisle = aisle_repo.get_by_id("aisle-1")
    assert updated_aisle is not None
    assert updated_aisle.status == AisleStatus.PROCESSED
    assert updated_aisle.error_code is None
    assert updated_aisle.error_message is None
    assert updated_aisle.retryable is None


def test_mark_success_sets_operational_job_id_for_production_inventory() -> None:
    """After a successful job, production aisles get operational_job_id = job_id (review slice alignment)."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id="j-prod-1",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
        )
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-prod",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        operational_job_id=None,
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = InMemoryInventoryRepo()
    inv_repo.save(
        Inventory(
            "inv-prod",
            "Prod WH",
            InventoryStatus.PROCESSING,
            now,
            now,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=noop,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=inv_repo,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )
    executor._state.mark_success("j-prod-1", aisle, Path("/tmp/run/hybrid_report.json"), run_metadata=None)
    saved = aisle_repo.get_by_id("aisle-1")
    assert saved is not None
    assert saved.operational_job_id == "j-prod-1"


def test_mark_success_overwrites_operational_job_id_on_subsequent_production_run() -> None:
    """Latest succeeded job becomes operational (policy: always set on success for production)."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    for jid in ("j-first", "j-second"):
        job_repo.save(
            Job(
                id=jid,
                target_type="aisle",
                target_id="aisle-1",
                job_type="process_aisle",
                status=JobStatus.RUNNING,
                payload_json={"aisle_id": "aisle-1"},
                created_at=now,
                updated_at=now,
            )
        )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-prod",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        operational_job_id="j-first",
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = InMemoryInventoryRepo()
    inv_repo.save(
        Inventory(
            "inv-prod",
            "Prod WH",
            InventoryStatus.PROCESSING,
            now,
            now,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=noop,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=inv_repo,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )
    executor._state.mark_success("j-second", aisle, Path("/tmp/run/hybrid_report.json"), run_metadata=None)
    assert aisle_repo.get_by_id("aisle-1") is not None
    assert aisle_repo.get_by_id("aisle-1").operational_job_id == "j-second"


def test_mark_success_does_not_set_operational_job_id_for_test_inventory() -> None:
    """Test inventories keep explicit promotion; executor does not set operational_job_id here."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id="j-test-1",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
        )
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-test",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        operational_job_id=None,
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = InMemoryInventoryRepo()
    inv_repo.save(
        Inventory(
            "inv-test",
            "Bench",
            InventoryStatus.PROCESSING,
            now,
            now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=noop,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=inv_repo,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )
    executor._state.mark_success("j-test-1", aisle, Path("/tmp/run/hybrid_report.json"), run_metadata=None)
    saved = aisle_repo.get_by_id("aisle-1")
    assert saved is not None
    assert saved.operational_job_id is None


def test_failed_job_does_not_update_operational_job_id() -> None:
    """Failure path must preserve existing operational pointer (no auto-repoint on failed run)."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id="j-fail-1",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
        )
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-prod",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        operational_job_id="j-prev-ok",
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = InMemoryInventoryRepo()
    inv_repo.save(
        Inventory(
            "inv-prod",
            "Prod WH",
            InventoryStatus.PROCESSING,
            now,
            now,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=noop,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=inv_repo,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )
    executor._state.fail_job_and_aisle("j-fail-1", aisle, "boom")
    saved = aisle_repo.get_by_id("aisle-1")
    assert saved is not None
    assert saved.status == AisleStatus.FAILED
    assert saved.operational_job_id == "j-prev-ok"


def test_mark_running_transitions_starting_job_to_running() -> None:
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id="job-running",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
        )
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.QUEUED,
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

    executor._state.mark_running("job-running", aisle, now)

    updated = job_repo.get_by_id("job-running")
    assert updated is not None
    assert updated.status == JobStatus.RUNNING
    assert updated.current_stage == "Pipeline"
    assert updated.current_substep == "startup_confirmed"


def test_update_runtime_status_only_resets_step_started_at_when_stage_or_substep_changes() -> None:
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    later = datetime(2025, 3, 17, 12, 1, 0, tzinfo=timezone.utc)
    much_later = datetime(2025, 3, 17, 12, 2, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id="job-steps",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
            current_stage="FrameAcquisitionStage",
            current_substep="image_open",
            current_step_started_at=now,
        )
    )
    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=InMemoryAisleRepo(),
        source_asset_repo=noop,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=clock,
        inventory_repo=noop,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )

    clock.set_now(later)
    executor._state.update_runtime_status("job-steps", stage="FrameAcquisitionStage", substep="image_open")
    unchanged = job_repo.get_by_id("job-steps")
    assert unchanged is not None
    assert unchanged.current_step_started_at == now

    clock.set_now(much_later)
    executor._state.update_runtime_status("job-steps", stage="FrameAcquisitionStage", substep="image_decode")
    changed = job_repo.get_by_id("job-steps")
    assert changed is not None
    assert changed.current_step_started_at == much_later


def test_heartbeat_reads_job_once_and_updates_timestamp() -> None:
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    later = datetime(2025, 3, 17, 12, 0, 10, tzinfo=timezone.utc)
    clock = FixedClock(later)
    job_repo = CountingJobRepo()
    job_repo.save(
        Job(
            id="job-heartbeat",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
            last_heartbeat_at=now,
        )
    )
    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=InMemoryAisleRepo(),
        source_asset_repo=noop,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=clock,
        inventory_repo=noop,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )

    updated = executor._state.heartbeat("job-heartbeat")

    assert updated is not None
    assert job_repo.get_calls == 1
    assert updated.last_heartbeat_at == later


def test_mark_success_persists_provider_and_prompt_key_in_result_json() -> None:
    """Phase 7: Successful job result_json includes provider and prompt_key when present in run_metadata."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job = Job(
        id="j-attribution",
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
        RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT: default_empty_block(),
        "provider": "gemini-2.0",
        "prompt_key": "global_v21",
    }
    report_path = Path("/tmp/run/hybrid_report.json")
    executor._state.mark_success("j-attribution", aisle, report_path, run_metadata=run_metadata)

    updated = job_repo.get_by_id("j-attribution")
    assert updated is not None
    assert updated.result_json is not None
    assert updated.result_json["report_path"] == str(report_path)
    assert updated.result_json["provider"] == "gemini-2.0"
    assert updated.result_json["prompt_key"] == "global_v21"
    assert updated.result_json.get("prompt_version") == "global_v21@v2.1"
    assert updated.prompt_version == "global_v21@v2.1"
    assert updated.result_json.get(RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT) is not None


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
        "provider": "test-provider",
        "prompt_key": "global_v21",
    }
    report_path = Path("/tmp/run/hybrid_report.json")
    executor._state.mark_success("j2", aisle, report_path, run_metadata=run_metadata)

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
    # Phase 7: provider and prompt_key persisted for run attribution
    assert updated.result_json.get("provider") == "test-provider"
    assert updated.result_json.get("prompt_key") == "global_v21"


def test_execute_persists_visual_reference_context_when_resolution_fails_before_pipeline(tmp_path: Path) -> None:
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "j-ref-resolution-fail"
    aisle_id = "aisle-1"
    job_repo = InMemoryJobRepo()
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.STARTING,
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

    base_path = tmp_path
    v3_base = base_path / "v3_uploads"
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "photo.jpg").write_bytes(b"fake")

    failing_context = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="ref-missing",
                source_path="inventories/inv-1/visual_references/ref-missing.jpg",
                mime_type="image/jpeg",
            )
        ],
        instructions=["Use references as context."],
    )

    with patch.object(executor._pipeline_runner, "build_analysis_context", return_value=failing_context):
        with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as mock_settings:
            mock_settings.return_value.output_dir = str(base_path)
            handled = executor.execute(base_path, job_id)

    assert handled is True
    updated_job = job_repo.get_by_id(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.FAILED
    assert updated_job.result_json is not None
    vrc = updated_job.result_json.get(RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT)
    assert vrc is not None
    assert vrc["resolved"] is False
    assert vrc["reference_ids"] == []
    assert vrc["resolved_count"] == 0
    assert vrc["provider_consumed"] is False
    assert vrc["provider_consumed_count"] == 0
    assert vrc["resolution_stage"] == "input_artifact_resolution"
    assert "visual reference ref-missing" in vrc["resolution_error"]


def test_execute_passes_resolved_visual_reference_context_to_pipeline(tmp_path: Path) -> None:
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "j-ref-context-resolved"
    aisle_id = "aisle-1"
    inventory_id = "inv-1"
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id=job_id,
            target_type="aisle",
            target_id=aisle_id,
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json={"aisle_id": aisle_id},
            created_at=now,
            updated_at=now,
        )
    )

    aisle = Aisle(
        id=aisle_id,
        inventory_id=inventory_id,
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)

    inventory_repo = InMemoryInventoryRepo()
    inventory_repo.save(Inventory(id=inventory_id, name="Inv", status=InventoryStatus.DRAFT, created_at=now, updated_at=now))
    reference_repo = InMemoryVisualReferenceRepo()
    reference = InventoryVisualReference(
        id="ref-1",
        inventory_id=inventory_id,
        filename="ref.jpg",
        storage_path="inventories/inv-1/visual_references/ref.jpg",
        mime_type="image/jpeg",
        file_size=7,
        created_at=now,
    )
    reference_repo.create(reference)

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
        inventory_repo=inventory_repo,
        inventory_visual_reference_repo=reference_repo,
        artifact_store=StubArtifactStorage(),
        raw_label_repo=noop,
    )

    base_path = tmp_path
    v3_base = base_path / "v3_uploads"
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "photo.jpg").write_bytes(b"fake")
    (v3_base / "inventories" / "inv-1" / "visual_references").mkdir(parents=True, exist_ok=True)
    (v3_base / "inventories" / "inv-1" / "visual_references" / "ref.jpg").write_bytes(b"ref")

    unresolved_context = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="ref-1",
                source_path="inventories/inv-1/visual_references/ref.jpg",
                mime_type="image/jpeg",
            )
        ],
        instructions=["Use references as context."],
    )
    captured: dict[str, AnalysisContext | None] = {"analysis_context": None}

    class FakePipeline:
        def process_video(self, _video_path, **kwargs):
            captured["analysis_context"] = kwargs.get("analysis_context")
            return PipelineRunResult(exit_code=1, run_metadata=None)

    with patch.object(executor._pipeline_runner, "build_analysis_context", return_value=unresolved_context):
        with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as mock_settings:
            mock_settings.return_value.output_dir = str(base_path)
            with patch("src.infrastructure.pipeline.v3_job_executor.HybridInventoryPipeline", return_value=FakePipeline()):
                handled = executor.execute(base_path, job_id)

    assert handled is True
    passed_context = captured["analysis_context"]
    assert passed_context is not None
    assert len(passed_context.visual_references) == 1
    assert passed_context.visual_references[0].resolved_path is not None
    assert Path(passed_context.visual_references[0].resolved_path).exists()


def test_reference_updates_affect_only_future_jobs_and_preserve_historical_traceability() -> None:
    now = datetime(2025, 4, 2, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    inventory_repo = InMemoryInventoryRepo()
    inventory_repo.save(
        Inventory(
            id="inv-1",
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
    )
    reference_repo = InMemoryVisualReferenceRepo()
    artifact_storage = StubArtifactStorage()
    upload_use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inventory_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
        clock=clock,
    )
    delete_use_case = DeleteInventoryVisualReferenceUseCase(
        inventory_repo=inventory_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
    )
    resolver = InventoryVisualReferenceResolver(inventory_repo, reference_repo)
    context_builder = AisleAnalysisContextBuilder(resolver)

    refs_a = upload_use_case.execute(
        "inv-1",
        [UploadedVisualReferenceFile("front-a.jpg", BytesIO(b"image-a"), "image/jpeg", size=7)],
    )
    ctx_a = context_builder.build(inventory_id="inv-1", primary_evidence=[], metadata=None)
    assert [ref.reference_id for ref in ctx_a.visual_references] == [refs_a[0].id]
    run_metadata_a = build_run_metadata(
        ctx_a,
        {
            "visual_references_consumed": True,
            "visual_reference_count": len(ctx_a.visual_references),
        },
    )

    job_repo = InMemoryJobRepo()
    aisle_repo = InMemoryAisleRepo()
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.PROCESSED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo.save(aisle)
    job_a = Job(
        id="job-a",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job_a)
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=NoopRepo(),
        position_repo=NoopRepo(),
        product_record_repo=NoopRepo(),
        evidence_repo=NoopRepo(),
        clock=clock,
        inventory_repo=inventory_repo,
        inventory_visual_reference_repo=reference_repo,
        raw_label_repo=NoopRepo(),
    )
    executor._state.mark_success("job-a", aisle, Path("/tmp/run-a/hybrid_report.json"), run_metadata=run_metadata_a)

    delete_use_case.execute("inv-1", refs_a[0].id)
    refs_b = upload_use_case.execute(
        "inv-1",
        [UploadedVisualReferenceFile("front-b.png", BytesIO(b"image-b"), "image/png", size=7)],
    )
    ctx_b = context_builder.build(inventory_id="inv-1", primary_evidence=[], metadata=None)
    assert [ref.reference_id for ref in ctx_b.visual_references] == [refs_b[0].id]
    run_metadata_b = build_run_metadata(
        ctx_b,
        {
            "visual_references_consumed": True,
            "visual_reference_count": len(ctx_b.visual_references),
        },
    )

    job_b = Job(
        id="job-b",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job_b)
    executor._state.mark_success("job-b", aisle, Path("/tmp/run-b/hybrid_report.json"), run_metadata=run_metadata_b)

    stored_job_a = job_repo.get_by_id("job-a")
    stored_job_b = job_repo.get_by_id("job-b")
    assert stored_job_a is not None
    assert stored_job_b is not None
    assert stored_job_a.result_json is not None
    assert stored_job_b.result_json is not None

    vrc_a = stored_job_a.result_json[RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT]
    vrc_b = stored_job_b.result_json[RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT]
    assert vrc_a["reference_ids"] == [refs_a[0].id]
    assert vrc_b["reference_ids"] == [refs_b[0].id]
    assert refs_a[0].id != refs_b[0].id
    assert vrc_a["provider_consumed_count"] == 1
    assert vrc_b["provider_consumed_count"] == 1
    assert [ref.id for ref in reference_repo.list_by_inventory("inv-1")] == [refs_b[0].id]


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
        status=JobStatus.STARTING,
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

    persist_uc = MagicMock()
    persist_uc.execute.side_effect = ValueError("simulated persist error")
    with patch.object(executor, "_persist_use_case", persist_uc):
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
                with patch.object(
                    executor._pipeline_runner,
                    "build_analysis_context",
                    return_value=AnalysisContext(
                        primary_evidence=[],
                        visual_references=[],
                        instructions="",
                    ),
                ):
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


def test_execute_rejects_running_status_reentry() -> None:
    """Corrected contract: executor accepts STARTING only, not re-entry from RUNNING."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "j-claimed-running"
    aisle_id = "aisle-1"
    job_repo = InMemoryJobRepo()
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.QUEUED,
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
    base_path = Path("/tmp/test_execute_running_status")
    base_path.mkdir(parents=True, exist_ok=True)
    artifact_root = base_path / "durable_artifact_root"
    artifact_store = V3ArtifactStorageAdapter(artifact_root)
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
        artifact_store=artifact_store,
    )

    (base_path / job_id).mkdir(parents=True, exist_ok=True)
    run_dir = base_path / job_id / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "hybrid_report.json").write_text(json.dumps({"entities": []}), encoding="utf-8")
    (run_dir / "execution_log.jsonl").write_text(
        '{"ts":"2025-01-01T00:00:00+00:00","stage":"test","level":"info","message":"ok"}\n',
        encoding="utf-8",
    )
    (run_dir / "hybrid_report.csv").write_text("col\nval\n", encoding="utf-8")
    v3_base = base_path / "v3_uploads"
    v3_base.mkdir(parents=True, exist_ok=True)
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "photo.jpg").write_bytes(b"fake")

    with patch.object(executor, "_persist_use_case", MagicMock(return_value=None)):
        with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as mock_settings:
            mock_settings.return_value.output_dir = str(base_path)
            with patch(
                "src.infrastructure.pipeline.v3_job_executor.HybridInventoryPipeline"
            ) as mock_pipeline_cls:
                mock_pipeline_cls.return_value.process_video.return_value = PipelineRunResult(
                    exit_code=0, run_metadata=None
                )
                with patch.object(
                    executor._pipeline_runner,
                    "build_analysis_context",
                    return_value=AnalysisContext(
                        primary_evidence=[],
                        visual_references=[],
                        instructions="",
                    ),
                ):
                    handled = executor.execute(base_path, job_id)

    assert handled is True
    updated_job = job_repo.get_by_id(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.RUNNING
    assert updated_job.result_json is None


def test_execute_cooperatively_cancels_when_cancel_requested_detected(tmp_path: Path) -> None:
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "j-cancel-during-execution"
    aisle_id = "aisle-1"
    job_repo = InMemoryJobRepo()
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.QUEUED,
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
    artifact_root = tmp_path / "durable_artifact_root"
    artifact_store = V3ArtifactStorageAdapter(artifact_root)
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
        artifact_store=artifact_store,
    )

    v3_base = tmp_path / "v3_uploads"
    v3_base.mkdir(parents=True, exist_ok=True)
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "photo.jpg").write_bytes(b"fake")

    def process_video_side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
        executing_job = job_repo.get_by_id(job_id)
        assert executing_job is not None
        executing_job.status = JobStatus.CANCEL_REQUESTED
        executing_job.cancel_requested_at = now
        job_repo.save(executing_job)
        # Real pipeline calls cancellation_checkpoint at stage boundaries; that raises
        # PipelineCancellationRequestedError when the job is cancel-requested.
        kwargs["cancellation_checkpoint"](
            "AnalysisStage",
            "provider_call",
            "cooperative cancel during analysis",
        )

    with patch.object(executor, "_persist_use_case", MagicMock(return_value=None)):
        with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as mock_settings:
            mock_settings.return_value.output_dir = str(tmp_path)
            with patch(
                "src.infrastructure.pipeline.v3_job_executor.HybridInventoryPipeline"
            ) as mock_pipeline_cls:
                mock_pipeline_cls.return_value.process_video.side_effect = process_video_side_effect
                with patch.object(
                    executor._pipeline_runner,
                    "build_analysis_context",
                    return_value=AnalysisContext(
                        primary_evidence=[],
                        visual_references=[],
                        instructions="",
                    ),
                ):
                    handled = executor.execute(tmp_path, job_id)

    assert handled is True
    updated_job = job_repo.get_by_id(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.CANCELED
    assert updated_job.failure_code == "CANCELED"
    assert updated_job.finished_at == now
    updated_aisle = aisle_repo.get_by_id(aisle_id)
    assert updated_aisle is not None
    assert updated_aisle.status == AisleStatus.FAILED
    assert updated_aisle.error_code == "CANCELED"
    run_log_path = tmp_path / job_id / RUN_ID / "execution_log.jsonl"
    log_text = run_log_path.read_text(encoding="utf-8")
    assert log_text.count("job.cancel_requested") >= 1
    assert log_text.count("job.cancel_detected") >= 1
    assert log_text.count("job.canceled") >= 1
    req_i = log_text.index("job.cancel_requested")
    det_i = log_text.index("job.cancel_detected")
    can_i = log_text.index("job.canceled")
    assert req_i < det_i < can_i


def test_run_context_cancellation_uses_injected_checkpoint_not_metadata_flag() -> None:
    observed: list[tuple[str, str | None, str]] = []

    def checkpoint(stage: str, substep: str | None, reason: str) -> None:
        observed.append((stage, substep, reason))

    context = RunContext(
        job_id="job-1",
        run_id="run",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/run"),
        job_input=JobInput(video_path="", mode="hybrid", input_type="video"),
        settings=object(),
        logger=MagicMock(),
        metadata={"cancel_requested": True},
        cancellation_checkpoint=checkpoint,
    )

    context.check_cancellation(stage="AnalysisStage", substep="provider_call", reason="repo-backed cancellation")

    assert observed == [("AnalysisStage", "provider_call", "repo-backed cancellation")]


def test_execute_durable_artifact_upload_failure_marks_job_failed() -> None:
    """Phase 3B: failed artifact upload must not mark job succeeded or write durable metadata."""
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "j-upload-fail"
    aisle_id = "aisle-1"
    job_repo = InMemoryJobRepo()
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.QUEUED,
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
    base_path = Path("/tmp/test_execute_upload_fail")
    base_path.mkdir(parents=True, exist_ok=True)
    artifact_root = base_path / "durable_artifact_root"
    artifact_store = V3ArtifactStorageAdapter(artifact_root)
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
        artifact_store=artifact_store,
    )

    (base_path / job_id).mkdir(parents=True, exist_ok=True)
    run_dir = base_path / job_id / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "hybrid_report.json").write_text(json.dumps({"entities": []}), encoding="utf-8")
    (run_dir / "execution_log.jsonl").write_text(
        '{"ts":"2025-01-01T00:00:00+00:00","stage":"test","level":"info","message":"ok"}\n',
        encoding="utf-8",
    )
    (run_dir / "hybrid_report.csv").write_text("c\n", encoding="utf-8")
    v3_base = base_path / "v3_uploads"
    v3_base.mkdir(parents=True, exist_ok=True)
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "photo.jpg").write_bytes(b"fake")

    with patch.object(artifact_store, "put_object", side_effect=RuntimeError("S3 unavailable")):
        with patch.object(executor, "_persist_use_case", MagicMock(return_value=None)):
            with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as mock_settings:
                mock_settings.return_value.output_dir = str(base_path)
                with patch(
                    "src.infrastructure.pipeline.v3_job_executor.HybridInventoryPipeline"
                ) as mock_pipeline_cls:
                    mock_pipeline_cls.return_value.process_video.return_value = PipelineRunResult(
                        exit_code=0, run_metadata=None
                    )
                    with patch.object(
                        executor._pipeline_runner,
                        "build_analysis_context",
                        return_value=AnalysisContext(
                            primary_evidence=[],
                            visual_references=[],
                            instructions="",
                        ),
                    ):
                        handled = executor.execute(base_path, job_id)

    assert handled is True
    updated_job = job_repo.get_by_id(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.FAILED
    assert updated_job.error_message is not None
    assert "Durable artifact upload failed" in updated_job.error_message
    assert updated_job.result_json is None or "durable_artifacts" not in (updated_job.result_json or {})


def test_execute_durable_upload_failure_after_persist_partial_finalization_explicit() -> None:
    """Ordering is pipeline → persist → durable upload → mark success.

    If durable upload fails, PersistAisleResult has already run; job/aisle are FAILED and
    result_json must not claim durable_artifacts (partial finalization — see executor comment).
    """
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "j-partial-finalize"
    aisle_id = "aisle-1"
    job_repo = InMemoryJobRepo()
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.QUEUED,
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
    base_path = Path("/tmp/test_partial_finalize")
    base_path.mkdir(parents=True, exist_ok=True)
    artifact_root = base_path / "durable_artifact_root"
    artifact_store = V3ArtifactStorageAdapter(artifact_root)
    persist_uc = MagicMock()
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
        artifact_store=artifact_store,
    )

    (base_path / job_id).mkdir(parents=True, exist_ok=True)
    run_dir = base_path / job_id / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "hybrid_report.json").write_text(json.dumps({"entities": []}), encoding="utf-8")
    (run_dir / "execution_log.jsonl").write_text(
        '{"ts":"2025-01-01T00:00:00+00:00","stage":"test","level":"info","message":"ok"}\n',
        encoding="utf-8",
    )
    (run_dir / "hybrid_report.csv").write_text("c\n", encoding="utf-8")
    v3_base = base_path / "v3_uploads"
    v3_base.mkdir(parents=True, exist_ok=True)
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "photo.jpg").write_bytes(b"fake")

    with patch.object(executor, "_persist_use_case", persist_uc):
        with patch.object(artifact_store, "put_object", side_effect=RuntimeError("upload unavailable")):
            with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as mock_settings:
                mock_settings.return_value.output_dir = str(base_path)
                with patch(
                    "src.infrastructure.pipeline.v3_job_executor.HybridInventoryPipeline"
                ) as mock_pipeline_cls:
                    mock_pipeline_cls.return_value.process_video.return_value = PipelineRunResult(
                        exit_code=0, run_metadata=None
                    )
                    with patch.object(
                        executor._pipeline_runner,
                        "build_analysis_context",
                        return_value=AnalysisContext(
                            primary_evidence=[],
                            visual_references=[],
                            instructions="",
                        ),
                    ):
                        executor.execute(base_path, job_id)

    persist_uc.execute.assert_called_once()
    updated_job = job_repo.get_by_id(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.FAILED
    assert "Durable artifact upload failed" in (updated_job.error_message or "")
    assert updated_job.result_json is None or "durable_artifacts" not in (updated_job.result_json or {})

    updated_aisle = aisle_repo.get_by_id(aisle_id)
    assert updated_aisle is not None
    assert updated_aisle.status == AisleStatus.FAILED


def test_execute_rejects_mixed_video_and_photo_assets() -> None:
    now = datetime(2025, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "j-mixed-assets"
    aisle_id = "aisle-1"
    job_repo = InMemoryJobRepo()
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)
    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.QUEUED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)

    class MixedAssetsRepo:
        def list_by_aisle(self, aid: str):
            if aid != aisle_id:
                return []
            return [
                SourceAsset(
                    id="asset-video",
                    aisle_id=aisle_id,
                    type=SourceAssetType.VIDEO,
                    original_filename="clip.mp4",
                    storage_path="a1/clip.mp4",
                    mime_type="video/mp4",
                    uploaded_at=now,
                ),
                SourceAsset(
                    id="asset-photo",
                    aisle_id=aisle_id,
                    type=SourceAssetType.PHOTO,
                    original_filename="p.jpg",
                    storage_path="a1/p.jpg",
                    mime_type="image/jpeg",
                    uploaded_at=now,
                ),
            ]

    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=MixedAssetsRepo(),
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=noop,
        inventory_visual_reference_repo=noop,
        raw_label_repo=noop,
    )

    base_path = Path("/tmp/test_execute_mixed_assets")
    base_path.mkdir(parents=True, exist_ok=True)
    (base_path / "v3_uploads" / "a1").mkdir(parents=True, exist_ok=True)
    (base_path / "v3_uploads" / "a1" / "clip.mp4").write_bytes(b"fake-video")
    (base_path / "v3_uploads" / "a1" / "p.jpg").write_bytes(b"fake-image")

    with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as mock_settings:
        mock_settings.return_value.output_dir = str(base_path)
        with patch.object(
            executor._pipeline_runner,
            "build_analysis_context",
            return_value=AnalysisContext(
                primary_evidence=[],
                visual_references=[],
                instructions="",
            ),
        ):
            handled = executor.execute(base_path, job_id)

    assert handled is True
    updated_job = job_repo.get_by_id(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.FAILED
    assert updated_job.error_message is not None
    assert "videos must be uploaded/processed as a single video asset" in updated_job.error_message
