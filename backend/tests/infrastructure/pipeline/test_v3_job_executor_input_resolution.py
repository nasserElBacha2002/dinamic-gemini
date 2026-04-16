from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional, Sequence

import pytest

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
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.infrastructure.pipeline.v3_job_executor import V3JobExecutor
from src.infrastructure.repositories.sql_source_asset_repository import _row_to_asset
from src.pipeline.contracts.analysis_context import AnalysisContext, VisualReferenceContext


def _runner_build_pipeline_input(
    ex: V3JobExecutor,
    assets: list,
    *,
    v3_base: Path,
    job_dir: Path,
    job_id: str,
    analysis_context: AnalysisContext,
    inventory_id: str,
):
    """Call runner input builder with the same ``run_id`` segment the executor uses in production."""
    return ex._pipeline_runner.build_pipeline_input(
        assets,
        v3_base,
        job_dir,
        job_id,
        analysis_context=analysis_context,
        inventory_id=inventory_id,
        run_id="run",
        legacy_local_read_enabled=True,
    )


class _Clock(Clock):
    def now(self):
        return datetime(2025, 3, 20, 12, 0, 0, tzinfo=timezone.utc)


class _NoopJobRepo(JobRepository):
    def save(self, job):  # type: ignore[no-untyped-def]
        return None

    def get_by_id(self, job_id: str):  # type: ignore[no-untyped-def]
        return None

    def get_latest_by_target(self, target_type: str, target_id: str):
        return None

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]):
        return {}

    def list_jobs_for_target(self, target_type: str, target_id: str, *, limit: int = 50):
        return []


class _NoopAisleRepo(AisleRepository):
    def save(self, aisle):  # type: ignore[no-untyped-def]
        return None

    def get_by_id(self, aisle_id: str):
        return None

    def list_by_inventory(self, inventory_id: str):
        return []

    def get_by_inventory_and_code(self, inventory_id: str, code: str):
        return None


class _NoopRepo(
    SourceAssetRepository,
    PositionRepository,
    ProductRecordRepository,
    EvidenceRepository,
    RawLabelRepository,
):
    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None

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
        return None

    def list_for_scope(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def replace_for_scope(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    def summarize_assets_for_aisles(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return {}


class _InventoryRepo(InventoryRepository):
    def __init__(self, inventory: Inventory) -> None:
        self._inventory = inventory

    def save(self, inventory: Inventory) -> None:
        self._inventory = inventory

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        if self._inventory.id == inventory_id:
            return self._inventory
        return None

    def list_all(self) -> Sequence[Inventory]:
        return [self._inventory]


class _VisualRepo(InventoryVisualReferenceRepository):
    def __init__(self, refs: Sequence[InventoryVisualReference]) -> None:
        self._refs = list(refs)

    def get_by_id(self, reference_id: str) -> Optional[InventoryVisualReference]:
        return next((r for r in self._refs if r.id == reference_id), None)

    def create(self, reference: InventoryVisualReference) -> None:
        self._refs.append(reference)

    def create_many(self, references: Sequence[InventoryVisualReference]) -> None:
        self._refs.extend(references)

    def list_by_inventory(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        return [r for r in self._refs if r.inventory_id == inventory_id]

    def update(self, reference: InventoryVisualReference) -> None:
        for i, existing in enumerate(self._refs):
            if existing.id == reference.id:
                self._refs[i] = reference
                return
        raise KeyError(reference.id)

    def delete(self, reference_id: str) -> None:
        self._refs = [r for r in self._refs if r.id != reference_id]


class _FakeArtifactStore:
    def __init__(self, objects: Dict[str, bytes]) -> None:
        self._objects = objects
        self.bucket = "bucket-a"
        self.download_calls: list[tuple[str, str, str]] = []
        self.get_object_calls = 0

    def get_object(self, key: str):
        self.get_object_calls += 1
        if key not in self._objects:
            raise RuntimeError(f"missing key: {key}")
        raise AssertionError("resolver should not call get_object in streaming mode")

    def object_size_bytes(self, key: str, *, bucket: Optional[str] = None) -> int:
        if key not in self._objects:
            raise RuntimeError(f"missing key: {key}")
        return len(self._objects[key])

    def download_to_path(self, key: str, target_path: Path, *, bucket: Optional[str] = None) -> None:
        if key not in self._objects:
            raise RuntimeError(f"missing key: {key}")
        self.download_calls.append((bucket or "", key, str(target_path)))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(self._objects[key])


def _executor(tmp_inventory_id: str, visual_refs: Sequence[InventoryVisualReference], artifact_store) -> V3JobExecutor:
    return V3JobExecutor(
        job_repo=_NoopJobRepo(),
        aisle_repo=_NoopAisleRepo(),
        source_asset_repo=_NoopRepo(),
        position_repo=_NoopRepo(),
        product_record_repo=_NoopRepo(),
        evidence_repo=_NoopRepo(),
        clock=_Clock(),
        inventory_repo=_InventoryRepo(
            Inventory(
                id=tmp_inventory_id,
                name="inv",
                status=InventoryStatus.DRAFT,
                created_at=datetime(2025, 3, 20, 12, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2025, 3, 20, 12, 0, 0, tzinfo=timezone.utc),
            )
        ),
        inventory_visual_reference_repo=_VisualRepo(visual_refs),
        artifact_store=artifact_store,
    )


def test_build_pipeline_input_downloads_s3_source_asset_to_temp_workspace(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    job_dir.mkdir(parents=True, exist_ok=True)
    store = _FakeArtifactStore({"uploads/aisles/a1/raw/asset-1.jpg": b"s3-photo"})
    ex = _executor("inv-1", [], store)
    asset = SourceAsset(
        id="asset-1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="a.jpg",
        storage_path="uploads/aisles/a1/raw/asset-1.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="uploads/aisles/a1/raw/asset-1.jpg",
    )
    job_input, _ = _runner_build_pipeline_input(ex,
        [asset],
        v3_base=tmp_path / "v3_uploads",
        job_dir=job_dir,
        job_id="job-1",
        analysis_context=AnalysisContext(primary_evidence=[], visual_references=[], instructions=[]),
        inventory_id="inv-1",
    )
    assert job_input.input_type == "photos"
    saved = job_dir / "input_photos" / "0000_asset-1.jpg"
    assert saved.exists()
    assert saved.read_bytes() == b"s3-photo"
    assert store.download_calls
    assert store.get_object_calls == 0


def test_build_pipeline_input_accepts_sql_mapped_source_asset_with_provider_metadata(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-sql-mapped"
    job_dir.mkdir(parents=True, exist_ok=True)
    store = _FakeArtifactStore({"uploads/aisles/a1/raw/asset-sql.jpg": b"s3-photo"})
    ex = _executor("inv-sql", [], store)
    asset = _row_to_asset(
        SimpleNamespace(
            id="asset-sql",
            aisle_id="a1",
            type="photo",
            original_filename="mapped.jpg",
            storage_path="legacy/asset-sql.jpg",
            storage_provider="s3",
            storage_bucket="bucket-a",
            storage_key="uploads/aisles/a1/raw/asset-sql.jpg",
            content_type="image/jpeg",
            file_size_bytes=8,
            etag="etag-1",
            mime_type="image/jpeg",
            uploaded_at=datetime.now(timezone.utc),
            metadata_json=None,
        )
    )

    job_input, _ = _runner_build_pipeline_input(ex,
        [asset],
        v3_base=tmp_path / "v3_uploads",
        job_dir=job_dir,
        job_id="job-sql-mapped",
        analysis_context=AnalysisContext(primary_evidence=[], visual_references=[], instructions=[]),
        inventory_id="inv-sql",
    )

    assert job_input.input_type == "photos"
    saved = job_dir / "input_photos" / "0000_asset-sql.jpg"
    assert saved.exists()
    assert saved.read_bytes() == b"s3-photo"
    assert asset.storage_provider == "s3"
    assert asset.storage_key == "uploads/aisles/a1/raw/asset-sql.jpg"


def test_build_pipeline_input_legacy_local_fallback_works_when_provider_absent(tmp_path: Path) -> None:
    legacy_base = tmp_path / "v3_uploads"
    (legacy_base / "legacy").mkdir(parents=True, exist_ok=True)
    (legacy_base / "legacy" / "asset.jpg").write_bytes(b"legacy")
    job_dir = tmp_path / "job-2"
    job_dir.mkdir(parents=True, exist_ok=True)
    ex = _executor("inv-2", [], _FakeArtifactStore({}))
    asset = SourceAsset(
        id="asset-2",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="b.jpg",
        storage_path="legacy/asset.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
    )
    _runner_build_pipeline_input(ex,
        [asset],
        v3_base=legacy_base,
        job_dir=job_dir,
        job_id="job-2",
        analysis_context=AnalysisContext(primary_evidence=[], visual_references=[], instructions=[]),
        inventory_id="inv-2",
    )
    assert (job_dir / "input_photos" / "0000_asset-2.jpg").read_bytes() == b"legacy"


def test_build_pipeline_input_resolves_local_provider_source_asset_without_bucket(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-local-asset"
    job_dir.mkdir(parents=True, exist_ok=True)
    store = _FakeArtifactStore({"uploads/aisles/a1/raw/asset-local.jpg": b"local-photo"})
    ex = _executor("inv-local-asset", [], store)
    asset = SourceAsset(
        id="asset-local",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="local.jpg",
        storage_path="uploads/aisles/a1/raw/asset-local.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="local",
        storage_bucket=None,
        storage_key="uploads/aisles/a1/raw/asset-local.jpg",
    )

    _runner_build_pipeline_input(ex,
        [asset],
        v3_base=tmp_path / "v3_uploads",
        job_dir=job_dir,
        job_id="job-local-asset",
        analysis_context=AnalysisContext(primary_evidence=[], visual_references=[], instructions=[]),
        inventory_id="inv-local-asset",
    )

    assert (job_dir / "input_photos" / "0000_asset-local.jpg").read_bytes() == b"local-photo"


def test_build_pipeline_input_resolves_s3_visual_references_to_temp_files(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-3"
    job_dir.mkdir(parents=True, exist_ok=True)
    ref = InventoryVisualReference(
        id="ref-1",
        inventory_id="inv-3",
        filename="ref.jpg",
        storage_path="inventories/inv-3/visual_references/ref-1.jpg",
        mime_type="image/jpeg",
        file_size=7,
        created_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="inventories/inv-3/visual_references/ref-1.jpg",
    )
    store = _FakeArtifactStore(
        {
            "uploads/aisles/a1/raw/asset-3.jpg": b"asset",
            "inventories/inv-3/visual_references/ref-1.jpg": b"refdata",
        }
    )
    ex = _executor("inv-3", [ref], store)
    asset = SourceAsset(
        id="asset-3",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="c.jpg",
        storage_path="uploads/aisles/a1/raw/asset-3.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="uploads/aisles/a1/raw/asset-3.jpg",
    )
    ctx = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="ref-1",
                source_path="inventories/inv-3/visual_references/ref-1.jpg",
                mime_type="image/jpeg",
            )
        ],
        instructions=[],
    )
    job_input, _ = _runner_build_pipeline_input(ex,
        [asset],
        v3_base=tmp_path / "v3_uploads",
        job_dir=job_dir,
        job_id="job-3",
        analysis_context=ctx,
        inventory_id="inv-3",
    )
    refs = job_input.metadata["analysis_context"]["visual_references"]  # type: ignore[index]
    resolved_path = Path(refs[0]["resolved_path"])
    assert resolved_path.exists()
    assert resolved_path.read_bytes() == b"refdata"
    assert any(call[1] == "inventories/inv-3/visual_references/ref-1.jpg" for call in store.download_calls)


def test_build_pipeline_input_resolves_local_provider_visual_reference_without_bucket(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-local-ref"
    job_dir.mkdir(parents=True, exist_ok=True)
    ref = InventoryVisualReference(
        id="ref-local",
        inventory_id="inv-local-ref",
        filename="ref-local.jpg",
        storage_path="inventories/inv-local-ref/visual_references/ref-local.jpg",
        mime_type="image/jpeg",
        file_size=8,
        created_at=datetime.now(timezone.utc),
        storage_provider="local",
        storage_bucket=None,
        storage_key="inventories/inv-local-ref/visual_references/ref-local.jpg",
    )
    store = _FakeArtifactStore(
        {
            "uploads/aisles/a1/raw/asset-local-ref.jpg": b"asset",
            "inventories/inv-local-ref/visual_references/ref-local.jpg": b"ref-local",
        }
    )
    ex = _executor("inv-local-ref", [ref], store)
    asset = SourceAsset(
        id="asset-local-ref",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="asset.jpg",
        storage_path="uploads/aisles/a1/raw/asset-local-ref.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="local",
        storage_bucket=None,
        storage_key="uploads/aisles/a1/raw/asset-local-ref.jpg",
    )
    ctx = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="ref-local",
                source_path="inventories/inv-local-ref/visual_references/ref-local.jpg",
                mime_type="image/jpeg",
            )
        ],
        instructions=[],
    )

    job_input, _ = _runner_build_pipeline_input(ex,
        [asset],
        v3_base=tmp_path / "v3_uploads",
        job_dir=job_dir,
        job_id="job-local-ref",
        analysis_context=ctx,
        inventory_id="inv-local-ref",
    )

    refs = job_input.metadata["analysis_context"]["visual_references"]  # type: ignore[index]
    resolved_path = Path(refs[0]["resolved_path"])
    assert resolved_path.exists()
    assert resolved_path.read_bytes() == b"ref-local"


def test_build_pipeline_input_missing_s3_object_fails_with_clear_error(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-4"
    job_dir.mkdir(parents=True, exist_ok=True)
    ex = _executor("inv-4", [], _FakeArtifactStore({}))
    asset = SourceAsset(
        id="asset-4",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="d.jpg",
        storage_path="uploads/aisles/a1/raw/asset-4.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="uploads/aisles/a1/raw/asset-4.jpg",
    )
    with pytest.raises(RuntimeError) as exc:
        _runner_build_pipeline_input(ex,
            [asset],
            v3_base=tmp_path / "v3_uploads",
            job_dir=job_dir,
            job_id="job-4",
            analysis_context=AnalysisContext(primary_evidence=[], visual_references=[], instructions=[]),
            inventory_id="inv-4",
        )
    msg = str(exc.value)
    assert "source asset asset-4" in msg
    assert "storage_key=uploads/aisles/a1/raw/asset-4.jpg" in msg


def test_build_pipeline_input_fails_when_source_asset_bucket_mismatch(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-5"
    job_dir.mkdir(parents=True, exist_ok=True)
    store = _FakeArtifactStore({"uploads/aisles/a1/raw/asset-5.jpg": b"s3-photo"})
    ex = _executor("inv-5", [], store)
    asset = SourceAsset(
        id="asset-5",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="e.jpg",
        storage_path="uploads/aisles/a1/raw/asset-5.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="other-bucket",
        storage_key="uploads/aisles/a1/raw/asset-5.jpg",
    )
    with pytest.raises(RuntimeError, match="bucket mismatch"):
        _runner_build_pipeline_input(ex,
            [asset],
            v3_base=tmp_path / "v3_uploads",
            job_dir=job_dir,
            job_id="job-5",
            analysis_context=AnalysisContext(primary_evidence=[], visual_references=[], instructions=[]),
            inventory_id="inv-5",
        )


def test_build_pipeline_input_fails_when_visual_reference_bucket_missing(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-6"
    job_dir.mkdir(parents=True, exist_ok=True)
    ref = InventoryVisualReference(
        id="ref-x",
        inventory_id="inv-6",
        filename="ref.jpg",
        storage_path="inventories/inv-6/visual_references/ref-x.jpg",
        mime_type="image/jpeg",
        file_size=7,
        created_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket=None,
        storage_key="inventories/inv-6/visual_references/ref-x.jpg",
    )
    store = _FakeArtifactStore({"uploads/aisles/a1/raw/asset-6.jpg": b"asset"})
    ex = _executor("inv-6", [ref], store)
    asset = SourceAsset(
        id="asset-6",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="f.jpg",
        storage_path="uploads/aisles/a1/raw/asset-6.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="uploads/aisles/a1/raw/asset-6.jpg",
    )
    ctx = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="ref-x",
                source_path="inventories/inv-6/visual_references/ref-x.jpg",
                mime_type="image/jpeg",
            )
        ],
        instructions=[],
    )
    with pytest.raises(RuntimeError, match="storage_bucket is missing"):
        _runner_build_pipeline_input(ex,
            [asset],
            v3_base=tmp_path / "v3_uploads",
            job_dir=job_dir,
            job_id="job-6",
            analysis_context=ctx,
            inventory_id="inv-6",
        )


def test_unsupported_mixed_assets_fail_before_visual_reference_download(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-7"
    job_dir.mkdir(parents=True, exist_ok=True)
    ref = InventoryVisualReference(
        id="ref-mixed",
        inventory_id="inv-7",
        filename="ref.jpg",
        storage_path="inventories/inv-7/visual_references/ref-mixed.jpg",
        mime_type="image/jpeg",
        file_size=7,
        created_at=datetime.now(timezone.utc),
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="inventories/inv-7/visual_references/ref-mixed.jpg",
    )
    store = _FakeArtifactStore(
        {
            "uploads/aisles/a1/raw/asset-video.mp4": b"video",
            "uploads/aisles/a1/raw/asset-photo.jpg": b"photo",
            "inventories/inv-7/visual_references/ref-mixed.jpg": b"ref",
        }
    )
    ex = _executor("inv-7", [ref], store)
    assets = [
        SourceAsset(
            id="asset-video",
            aisle_id="a1",
            type=SourceAssetType.VIDEO,
            original_filename="x.mp4",
            storage_path="uploads/aisles/a1/raw/asset-video.mp4",
            mime_type="video/mp4",
            uploaded_at=datetime.now(timezone.utc),
            storage_provider="s3",
            storage_bucket="bucket-a",
            storage_key="uploads/aisles/a1/raw/asset-video.mp4",
        ),
        SourceAsset(
            id="asset-photo",
            aisle_id="a1",
            type=SourceAssetType.PHOTO,
            original_filename="x.jpg",
            storage_path="uploads/aisles/a1/raw/asset-photo.jpg",
            mime_type="image/jpeg",
            uploaded_at=datetime.now(timezone.utc),
            storage_provider="s3",
            storage_bucket="bucket-a",
            storage_key="uploads/aisles/a1/raw/asset-photo.jpg",
        ),
    ]
    with pytest.raises(ValueError, match="single video asset"):
        _runner_build_pipeline_input(ex,
            assets,
            v3_base=tmp_path / "v3_uploads",
            job_dir=job_dir,
            job_id="job-7",
            analysis_context=AnalysisContext(
                primary_evidence=[],
                visual_references=[
                    VisualReferenceContext(
                        reference_id="ref-mixed",
                        source_path="inventories/inv-7/visual_references/ref-mixed.jpg",
                        mime_type="image/jpeg",
                    )
                ],
                instructions=[],
            ),
            inventory_id="inv-7",
        )
    assert store.download_calls == []
