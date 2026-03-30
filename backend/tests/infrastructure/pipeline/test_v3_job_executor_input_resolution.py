from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
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
from src.pipeline.contracts.analysis_context import AnalysisContext, VisualReferenceContext

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

    def list_by_position(self, *args, **kwargs):  # type: ignore[no-untyped-def]
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

    def create(self, reference: InventoryVisualReference) -> None:
        self._refs.append(reference)

    def create_many(self, references: Sequence[InventoryVisualReference]) -> None:
        self._refs.extend(references)

    def list_by_inventory(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        return [r for r in self._refs if r.inventory_id == inventory_id]


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
    job_input, _ = ex._build_pipeline_input(  # type: ignore[attr-defined]
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
    ex._build_pipeline_input(  # type: ignore[attr-defined]
        [asset],
        v3_base=legacy_base,
        job_dir=job_dir,
        job_id="job-2",
        analysis_context=AnalysisContext(primary_evidence=[], visual_references=[], instructions=[]),
        inventory_id="inv-2",
    )
    assert (job_dir / "input_photos" / "0000_asset-2.jpg").read_bytes() == b"legacy"


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
    job_input, _ = ex._build_pipeline_input(  # type: ignore[attr-defined]
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
        ex._build_pipeline_input(  # type: ignore[attr-defined]
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
        ex._build_pipeline_input(  # type: ignore[attr-defined]
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
        ex._build_pipeline_input(  # type: ignore[attr-defined]
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
        ex._build_pipeline_input(  # type: ignore[attr-defined]
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
