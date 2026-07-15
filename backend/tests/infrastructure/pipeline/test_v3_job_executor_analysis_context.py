"""Tests for V3JobExecutor analysis context wiring — v3.2.4."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.application.ports.clock import Clock
from src.application.ports.contracts import AisleAssetRollup
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    SourceAssetRepository,
    SupplierReferenceImageRepository,
)
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.client_supplier.reference_image import SupplierReferenceImage
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_executor import V3JobExecutor
from tests.support.worker_phase2.executor_persist_deps import memory_executor_persist_kwargs


class FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class InMemoryJobRepo(JobRepository):
    def __init__(self) -> None:
        self._store: dict[str, Job] = {}

    def save(self, job: Job) -> None:
        self._store[job.id] = job

    def get_by_id(self, job_id: str) -> Job | None:
        return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        return None

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> dict[str, Job]:
        return {}

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        return []


class InMemoryAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        return None


class InMemoryInventoryRepo(InventoryRepository):
    def __init__(self) -> None:
        self._store: dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class InMemorySourceAssetRepo(SourceAssetRepository):
    def __init__(self) -> None:
        self._store: dict[str, SourceAsset] = {}

    def save(self, asset: SourceAsset) -> None:
        self._store[asset.id] = asset

    def get_by_id(self, asset_id: str) -> SourceAsset | None:
        return self._store.get(asset_id)

    def delete_by_id(self, asset_id: str) -> bool:
        if asset_id in self._store:
            del self._store[asset_id]
            return True
        return False

    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> SourceAsset | None:
        return None

    def get_by_upload_idempotency_key(
        self, aisle_id: str, upload_batch_id: str, upload_client_file_id: str
    ) -> SourceAsset | None:
        return None

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        return [a for a in self._store.values() if a.aisle_id == aisle_id]

    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> dict[str, AisleAssetRollup]:
        wanted = set(aisle_ids)
        by_aisle: dict[str, list[SourceAsset]] = defaultdict(list)
        for a in self._store.values():
            if a.aisle_id in wanted:
                by_aisle[a.aisle_id].append(a)
        out: dict[str, AisleAssetRollup] = {}
        for aid, assets in by_aisle.items():
            if not assets:
                continue
            last = max(x.uploaded_at for x in assets)
            out[aid] = AisleAssetRollup(count=len(assets), last_uploaded_at=last)
        return out


class InMemorySupplierReferenceImageRepo(SupplierReferenceImageRepository):
    def __init__(self) -> None:
        self._store: dict[str, SupplierReferenceImage] = {}

    def get_by_id(self, reference_image_id: str) -> SupplierReferenceImage | None:
        return self._store.get(reference_image_id)

    def create(self, reference_image: SupplierReferenceImage) -> None:
        self._store[reference_image.id] = reference_image

    def create_many(self, reference_images: Sequence[SupplierReferenceImage]) -> None:
        for img in reference_images:
            self._store[img.id] = img

    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierReferenceImage]:
        refs = [r for r in self._store.values() if r.client_supplier_id == client_supplier_id]
        refs.sort(key=lambda r: (r.created_at, r.id))
        return refs

    def delete(self, reference_image_id: str) -> None:
        self._store.pop(reference_image_id, None)


class NoopRepo(
    EvidenceRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
):
    def save(self, *args, **kwargs):  # type: ignore[override]
        return None

    def get_by_id(self, *args, **kwargs):  # type: ignore[override]
        return None

    def list_by_aisle(self, *args, **kwargs):  # type: ignore[override]
        return []

    def list_by_position(self, *args, **kwargs):  # type: ignore[override]
        return []

    def save_many(self, *args, **kwargs):  # type: ignore[override]
        return None

    def list_for_scope(self, *args, **kwargs):  # type: ignore[override]
        return []

    def replace_for_scope(self, *args, **kwargs):  # type: ignore[override]
        return None


class DummyRecomputeCounts(RecomputeConsolidatedCountsUseCase):
    def execute(self, inventory_id: str) -> None:  # type: ignore[override]
        return None


@pytest.mark.skip(
    reason="Integration-style test; enable when filesystem and pipeline are available in CI."
)
def test_v3_job_executor_injects_analysis_context_metadata(tmp_path: Path) -> None:
    """Smoke test: when executing, JobInput.metadata carries analysis_context with visual_references."""
    now = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    job_repo = InMemoryJobRepo()
    aisle_repo = InMemoryAisleRepo()
    inv_repo = InMemoryInventoryRepo()
    asset_repo = InMemorySourceAssetRepo()
    supplier_repo = InMemorySupplierReferenceImageRepo()
    noop = NoopRepo()

    inv = Inventory(
        id="inv-1",
        name="Inv",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id="client-1",
    )
    inv_repo.save(inv)

    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        client_supplier_id="sup-1",
    )
    aisle_repo.save(aisle)

    asset = SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="f.jpg",
        storage_path="some/path/f.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
        metadata_json=None,
    )
    asset_repo.save(asset)

    supplier_repo.create(
        SupplierReferenceImage(
            id="ref-1",
            client_supplier_id="sup-1",
            filename="ref.jpg",
            storage_path="inventories/inv-1/visual_references/ref-1.jpg",
            mime_type="image/jpeg",
            file_size=10,
            created_at=now,
            updated_at=now,
        )
    )

    payload = {"aisle_id": "aisle-1"}
    job = Job(
        id="job-1",
        payload_json=payload,
        status=JobStatus.QUEUED,
        created_at=now,
        updated_at=now,
        job_type="process_aisle",
        mode="hybrid",
        confidence_threshold=0.7,
    )
    job_repo.save(job)

    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=asset_repo,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=clock,
        inventory_repo=inv_repo,
        supplier_reference_image_repo=supplier_repo,
        **memory_executor_persist_kwargs(raw_label_repo=noop),
    )

    # We don't actually run the full pipeline in this test; we only assert that
    # the pipeline runner attaches analysis_context to JobInput.metadata.
    analysis_context = executor._pipeline_runner.build_analysis_context(
        aisle,
        inventory_client_id=inv.client_id,
    )
    (tmp_path / "some" / "path").mkdir(parents=True, exist_ok=True)
    (tmp_path / "some" / "path" / "f.jpg").write_bytes(b"asset")
    (tmp_path / "inventories" / "inv-1" / "visual_references").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inventories" / "inv-1" / "visual_references" / "ref-1.jpg").write_bytes(b"ref")
    job_input, _ = executor._pipeline_runner.build_pipeline_input(
        [asset],
        tmp_path,
        tmp_path,
        "job-1",
        analysis_context=analysis_context,
        aisle=aisle,
        run_id="run",
        legacy_local_read_enabled=True,
    )

    assert job_input.metadata is not None
    ctx = job_input.metadata.get("analysis_context")
    assert ctx is not None
    assert isinstance(ctx, dict)
    assert "visual_references" in ctx
    assert ctx["visual_references"]
