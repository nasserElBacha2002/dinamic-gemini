"""Behavior tests for :class:`V3ProcessAislePipelineRunner` (Phase 2 pipeline boundary)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.ports.repositories import SupplierReferenceImageRepository
from src.application.services.aisle_analysis_context_builder import (
    SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_INVENTORY_WITHOUT_CLIENT,
    AisleAnalysisContextBuilder,
)
from src.application.services.supplier_reference_image_resolver import (
    SupplierReferenceImageResolver,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.client_supplier.reference_image import SupplierReferenceImage
from src.infrastructure.pipeline.v3_process_aisle_pipeline_runner import (
    V3ProcessAislePipelineRunner,
    resolve_visual_reference_paths,
)
from src.infrastructure.repositories.memory_supplier_reference_image_repository import (
    MemorySupplierReferenceImageRepository,
)
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    VisualReferenceContext,
    analysis_context_to_dict,
)
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult


def _aisle(*, inv: str = "inv-1", supplier_id: str | None = None) -> Aisle:
    now = datetime.now(timezone.utc)
    return Aisle(
        id="aisle-1",
        inventory_id=inv,
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        client_supplier_id=supplier_id,
    )


def test_e5_inventory_without_client_skips_supplier_reference_images(tmp_path: Path) -> None:
    """E5: no inventory client — supplier rows exist but visual references must stay empty."""
    now = datetime.now(timezone.utc)
    supplier_repo = MemorySupplierReferenceImageRepository()
    supplier_repo.create(
        SupplierReferenceImage(
            id="sr-1",
            client_supplier_id="sup-1",
            filename="ref.jpg",
            storage_path="sub/ref.jpg",
            mime_type="image/jpeg",
            file_size=5,
            created_at=now,
            updated_at=now,
        )
    )
    context_builder = AisleAnalysisContextBuilder(SupplierReferenceImageResolver(supplier_repo))
    runner = V3ProcessAislePipelineRunner(
        supplier_reference_image_repo=supplier_repo,
        artifact_store=None,
        context_builder=context_builder,
    )
    aisle = _aisle(inv="inv-1", supplier_id="sup-1")
    ctx = runner.build_analysis_context(aisle, inventory_client_id=None)
    assert ctx.visual_references == []
    meta = ctx.metadata or {}
    assert meta.get("supplier_reference_resolution_status") == (
        SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_INVENTORY_WITHOUT_CLIENT
    )


def test_c71_supplier_pipeline_resolves_supplier_reference_images(tmp_path: Path) -> None:
    """v3 aisle processing resolves references exclusively via supplier_reference_images."""
    now = datetime.now(timezone.utc)
    supplier_repo = MemorySupplierReferenceImageRepository()
    supplier_repo.create(
        SupplierReferenceImage(
            id="sr-1",
            client_supplier_id="sup-1",
            filename="ref.jpg",
            storage_path="sub/ref.jpg",
            mime_type="image/jpeg",
            file_size=5,
            created_at=now,
            updated_at=now,
        )
    )

    context_builder = AisleAnalysisContextBuilder(SupplierReferenceImageResolver(supplier_repo))
    runner = V3ProcessAislePipelineRunner(
        supplier_reference_image_repo=supplier_repo,
        artifact_store=None,
        context_builder=context_builder,
    )
    aisle = _aisle(inv="inv-1", supplier_id="sup-1")

    v3_base = tmp_path / "v3_uploads"
    (v3_base / "sub").mkdir(parents=True)
    (v3_base / "sub" / "ref.jpg").write_bytes(b"ref-bytes")
    (v3_base / "sub" / "pic.jpg").write_bytes(b"pic-bytes")

    asset = SourceAsset(
        id="asset-1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="pic.jpg",
        storage_path="sub/pic.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )

    analysis_ctx = runner.build_analysis_context(aisle, inventory_client_id="client-1")
    assert len(analysis_ctx.visual_references) == 1

    job_dir = tmp_path / "job"
    job_dir.mkdir()

    job_input, video_path = runner.build_pipeline_input(
        [asset],
        v3_base,
        job_dir,
        "job-1",
        analysis_context=analysis_ctx,
        aisle=aisle,
        run_id="run",
        legacy_local_read_enabled=True,
    )

    assert video_path == ""
    assert (job_input.metadata or {}).get("inventory_id") == "inv-1"
    assert (job_input.metadata or {}).get("aisle_id") == "aisle-1"
    meta_ctx = (job_input.metadata or {}).get("analysis_context")
    assert isinstance(meta_ctx, dict)
    refs = meta_ctx.get("visual_references")
    assert isinstance(refs, list) and len(refs) == 1
    assert refs[0].get("resolved_path")


def test_c71_supplier_with_no_images_builds_empty_visual_references(tmp_path: Path) -> None:
    """C7.1: supplier id present but zero reference rows — no legacy fallback."""
    now = datetime.now(timezone.utc)
    supplier_repo = MagicMock(spec=SupplierReferenceImageRepository)
    supplier_repo.list_by_supplier.return_value = []

    context_builder = AisleAnalysisContextBuilder(SupplierReferenceImageResolver(supplier_repo))
    runner = V3ProcessAislePipelineRunner(
        supplier_reference_image_repo=supplier_repo,
        artifact_store=None,
        context_builder=context_builder,
    )
    aisle = _aisle(inv="inv-1", supplier_id="sup-1")

    v3_base = tmp_path / "v3_uploads"
    (v3_base / "sub").mkdir(parents=True)
    (v3_base / "sub" / "pic.jpg").write_bytes(b"pic")

    asset = SourceAsset(
        id="asset-1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="pic.jpg",
        storage_path="sub/pic.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )

    analysis_ctx = runner.build_analysis_context(aisle, inventory_client_id="client-1")
    assert analysis_ctx.visual_references == []

    job_dir = tmp_path / "job"
    job_dir.mkdir()

    job_input, _ = runner.build_pipeline_input(
        [asset],
        v3_base,
        job_dir,
        "job-1",
        analysis_context=analysis_ctx,
        aisle=aisle,
        run_id="run",
        legacy_local_read_enabled=True,
    )

    assert supplier_repo.list_by_supplier.call_count == 2
    assert all(c.args == ("sup-1",) for c in supplier_repo.list_by_supplier.call_args_list)
    meta_ctx = (job_input.metadata or {}).get("analysis_context")
    assert isinstance(meta_ctx, dict)
    assert meta_ctx.get("visual_references") == []


def test_c71_no_supplier_skips_supplier_repo_lookup_and_legacy_fallback(tmp_path: Path) -> None:
    """C7.1: null client_supplier_id — zero refs without supplier repo access."""
    now = datetime.now(timezone.utc)
    supplier_repo = MagicMock(spec=SupplierReferenceImageRepository)

    context_builder = AisleAnalysisContextBuilder(SupplierReferenceImageResolver(supplier_repo))
    runner = V3ProcessAislePipelineRunner(
        supplier_reference_image_repo=supplier_repo,
        artifact_store=None,
        context_builder=context_builder,
    )
    aisle = _aisle(inv="inv-1", supplier_id=None)

    v3_base = tmp_path / "v3_uploads"
    (v3_base / "sub").mkdir(parents=True)
    (v3_base / "sub" / "pic.jpg").write_bytes(b"pic")

    asset = SourceAsset(
        id="asset-1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="pic.jpg",
        storage_path="sub/pic.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )

    analysis_ctx = runner.build_analysis_context(aisle, inventory_client_id="client-1")
    assert analysis_ctx.visual_references == []
    supplier_repo.list_by_supplier.assert_not_called()

    job_dir = tmp_path / "job"
    job_dir.mkdir()

    job_input, _ = runner.build_pipeline_input(
        [asset],
        v3_base,
        job_dir,
        "job-1",
        analysis_context=analysis_ctx,
        aisle=aisle,
        run_id="run",
        legacy_local_read_enabled=True,
    )

    supplier_repo.list_by_supplier.assert_not_called()
    meta_ctx = (job_input.metadata or {}).get("analysis_context")
    assert isinstance(meta_ctx, dict)
    assert meta_ctx.get("visual_references") == []


def test_build_pipeline_input_rejects_multi_video_or_mixed_video_sets() -> None:
    runner = V3ProcessAislePipelineRunner(
        supplier_reference_image_repo=MagicMock(),
        artifact_store=None,
        context_builder=MagicMock(spec=AisleAnalysisContextBuilder),
    )
    v1 = SourceAsset(
        id="v1",
        aisle_id="a1",
        type=SourceAssetType.VIDEO,
        original_filename="a.mp4",
        storage_path="p/a.mp4",
        mime_type="video/mp4",
        uploaded_at=datetime.now(timezone.utc),
    )
    v2 = SourceAsset(
        id="v2",
        aisle_id="a1",
        type=SourceAssetType.VIDEO,
        original_filename="b.mp4",
        storage_path="p/b.mp4",
        mime_type="video/mp4",
        uploaded_at=datetime.now(timezone.utc),
    )
    ctx = AnalysisContext(primary_evidence=[], visual_references=[], instructions=[])
    with pytest.raises(ValueError, match="single video asset"):
        runner.build_pipeline_input(
            [v1, v2],
            Path("/tmp/v3"),
            Path("/tmp/job"),
            "job-1",
            analysis_context=ctx,
            aisle=_aisle(),
            run_id="run",
            legacy_local_read_enabled=True,
        )


def test_build_pipeline_input_photos_writes_manifest_and_job_input(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    v3_base = tmp_path / "v3_uploads"
    (v3_base / "sub").mkdir(parents=True)
    (v3_base / "sub" / "pic.jpg").write_bytes(b"img")
    asset = SourceAsset(
        id="asset-1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="pic.jpg",
        storage_path="sub/pic.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )
    ref_repo = MagicMock()
    ref_repo.list_by_supplier.return_value = []
    cb = MagicMock(spec=AisleAnalysisContextBuilder)
    ac = AnalysisContext(primary_evidence=[], visual_references=[], instructions=[])
    cb.build.return_value = ac
    runner = V3ProcessAislePipelineRunner(
        supplier_reference_image_repo=ref_repo,
        artifact_store=None,
        context_builder=cb,
    )
    job_dir = tmp_path / "job-1"
    job_dir.mkdir()
    job_input, video_path = runner.build_pipeline_input(
        [asset],
        v3_base,
        job_dir,
        "job-1",
        analysis_context=ac,
        aisle=_aisle(supplier_id=None),
        run_id="run",
        legacy_local_read_enabled=True,
    )
    assert video_path == ""
    assert job_input.input_type == "photos"
    assert job_input.input_manifest_path == "input_manifest.json"
    assert job_input.photos_dir == "input_photos"
    manifest = json.loads((job_dir / "input_manifest.json").read_text(encoding="utf-8"))
    assert manifest["input_type"] == "photos"
    assert len(manifest["photos"]) == 1
    assert manifest["photos"][0]["image_id"] == "asset-1"
    assert (job_dir / "input_photos" / "0000_asset-1.jpg").read_bytes() == b"img"


def test_resolve_visual_reference_paths_sets_resolved_path_from_resolver(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    ref_rec = SupplierReferenceImage(
        id="ref-1",
        client_supplier_id="sup-1",
        filename="r.jpg",
        storage_path="inventories/inv-1/visual_references/r.jpg",
        mime_type="image/jpeg",
        file_size=1,
        created_at=now,
        updated_at=now,
    )
    ctx = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="ref-1",
                source_path="inventories/inv-1/visual_references/r.jpg",
                mime_type="image/jpeg",
            )
        ],
        instructions=[],
    )
    target = tmp_path / "out" / "0000_ref-1.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"r")
    resolver = MagicMock()
    resolver.resolve_visual_reference.return_value = target
    out = resolve_visual_reference_paths(
        ctx,
        resolver=resolver,
        references_by_id={"ref-1": ref_rec},
        target_dir=tmp_path / "out",
    )
    assert len(out.visual_references) == 1
    assert out.visual_references[0].resolved_path == str(target)
    resolver.resolve_visual_reference.assert_called_once()


def test_run_hybrid_pipeline_delegates_to_process_video_with_executor_kwds() -> None:
    runner = V3ProcessAislePipelineRunner(
        supplier_reference_image_repo=MagicMock(),
        artifact_store=None,
        context_builder=MagicMock(),
    )
    pipeline = MagicMock()
    pipeline.process_video.return_value = PipelineRunResult(0, {"k": 1})
    settings = MagicMock()
    log = logging.getLogger("test-runner")
    ji = JobInput(
        video_path="",
        mode="hybrid",
        input_type="photos",
        metadata={
            "analysis_context": analysis_context_to_dict(
                AnalysisContext(primary_evidence=[], visual_references=[], instructions=[])
            )
        },
    )
    ac = AnalysisContext(primary_evidence=[], visual_references=[], instructions=[])

    def observer(stage: str, substep: str | None, event: str, details: dict | None) -> None:
        return None

    def checkpoint(stage: str, substep: str | None, reason: str) -> None:
        return None

    out = runner.run_hybrid_pipeline(
        pipeline=pipeline,
        video_path="",
        job_id="job-x",
        base_path=Path("/tmp/base"),
        run_id="run",
        settings=settings,
        job_input=ji,
        analysis_context=ac,
        log=log,
        execution_observer=observer,
        cancellation_checkpoint=checkpoint,
        pipeline_provider_name="prov",
        job_model_name="model",
        job_prompt_key="pk",
        job_prompt_version="pv",
        job_prompt_parity_mode=True,
    )
    assert out.exit_code == 0
    pipeline.process_video.assert_called_once()
    pos, kw = pipeline.process_video.call_args
    assert pos[0] == ""
    assert kw["mode"] == "hybrid"
    assert kw["settings"] is settings
    assert kw["video_id"] == "job-x"
    assert kw["output_path"] == Path("/tmp/base")
    assert kw["run_id"] == "run"
    assert kw["logger"] is log
    assert kw["progress_callback"] is None
    assert kw["job_input"] is ji
    assert kw["analysis_context"] is ac
    assert kw["execution_observer"] is observer
    assert kw["cancellation_checkpoint"] is checkpoint
    assert kw["pipeline_provider_name"] == "prov"
    assert kw["job_model_name"] == "model"
    assert kw["job_prompt_key"] == "pk"
    assert kw["job_prompt_version"] == "pv"
    assert kw["job_prompt_parity_mode"] is True
