"""Coordinator tests: :class:`V3JobExecutor` delegates to Phase 2 collaborators (spies, not full E2E)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_executor import RUN_ID, V3JobExecutor
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_to_dict
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult
from tests.infrastructure.pipeline.test_v3_job_executor_phase5 import (
    FixedClock,
    InMemoryAisleRepo,
    InMemoryInventoryRepo,
    InMemoryJobRepo,
    NoopRepo,
    StubArtifactStorage,
)
from tests.support.worker_phase2.executor_persist_deps import memory_executor_persist_kwargs


def test_execute_success_invokes_state_runner_and_artifacts(tmp_path: Path) -> None:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "coord-success"
    aisle_id = "aisle-1"
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
            execution_id="ex-1",
        )
    )
    aisle_repo = InMemoryAisleRepo()
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
    inv_repo = InMemoryInventoryRepo()
    inv_repo.save(
        Inventory(
            id="inv-1",
            name="Inv",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )

    class _OnePhotoRepo:
        def list_by_aisle(self, aid: str) -> Sequence[SourceAsset]:
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
        source_asset_repo=_OnePhotoRepo(),
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=inv_repo,
        supplier_reference_image_repo=noop,
        artifact_store=StubArtifactStorage(),
        **memory_executor_persist_kwargs(raw_label_repo=noop),
    )
    v3_base = tmp_path / "v3_uploads"
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "photo.jpg").write_bytes(b"x")

    real_state = executor._state
    real_artifacts = executor._artifacts
    spy_state = MagicMock(wraps=real_state)
    spy_runner = MagicMock()
    spy_artifacts = MagicMock(wraps=real_artifacts)

    ac = AnalysisContext(primary_evidence=[], visual_references=[], instructions=[])
    spy_runner.build_analysis_context.return_value = ac
    spy_runner.build_pipeline_input.return_value = (
        JobInput(
            video_path="/tmp/video.mp4",
            mode="hybrid",
            input_type="video",
            input_manifest_path="input_manifest.json",
            photos_dir="input_photos",
            metadata={"analysis_context": analysis_context_to_dict(ac)},
        ),
        "",
    )

    def _run_side_effect(**kwargs: object) -> PipelineRunResult:
        bp = kwargs["base_path"]
        assert isinstance(bp, Path)
        jid = kwargs["job_id"]
        run_dir = bp / str(jid) / RUN_ID
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "execution_log.jsonl").write_bytes(b"{}\n")
        (run_dir / "hybrid_report.json").write_text("{}", encoding="utf-8")
        return PipelineRunResult(0, {})

    spy_runner.run_hybrid_pipeline.side_effect = _run_side_effect

    executor._state = spy_state
    executor._preparation_service._state = spy_state
    executor._monitoring_service._state = spy_state
    executor._pipeline_runner = spy_runner
    executor._artifacts = spy_artifacts
    executor._persist_use_case = MagicMock()

    class _FakePipeline:
        def process_video(self, *args: object, **kwargs: object) -> PipelineRunResult:
            raise AssertionError("executor should use runner.run_hybrid_pipeline")

    with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as ms:
        ms.return_value.output_dir = str(tmp_path)
        ms.return_value.artifact_storage_legacy_local_read_enabled = True
        with patch(
            "src.infrastructure.pipeline.v3_job_executor.HybridInventoryPipeline",
            return_value=_FakePipeline(),
        ):
            assert executor.execute(tmp_path, job_id) is True

    spy_state.mark_running.assert_called_once()
    spy_runner.build_analysis_context.assert_called_once()
    spy_runner.build_pipeline_input.assert_called_once()
    spy_runner.run_hybrid_pipeline.assert_called_once()
    spy_artifacts.require_store.assert_called_once()
    spy_artifacts.publish_worker_durables.assert_called_once()
    spy_state.finalize_success.assert_called_once()
    executor._persist_use_case.execute.assert_called_once()


def test_execute_nonzero_pipeline_exit_delegates_fail_job_and_aisle(tmp_path: Path) -> None:
    now = datetime(2026, 3, 2, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "coord-fail-pipe"
    aisle_id = "aisle-2"
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
            execution_id="ex-2",
        )
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id="inv-1",
            code="A02",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    inv_repo = InMemoryInventoryRepo()
    inv_repo.save(
        Inventory(
            id="inv-1",
            name="Inv",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )

    class _OnePhotoRepo:
        def list_by_aisle(self, aid: str) -> Sequence[SourceAsset]:
            if aid != aisle_id:
                return []
            return [
                SourceAsset(
                    id="asset-2",
                    aisle_id=aisle_id,
                    type=SourceAssetType.PHOTO,
                    original_filename="p.jpg",
                    storage_path="a1/p.jpg",
                    mime_type="image/jpeg",
                    uploaded_at=now,
                )
            ]

    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=_OnePhotoRepo(),
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=inv_repo,
        supplier_reference_image_repo=noop,
        artifact_store=StubArtifactStorage(),
        **memory_executor_persist_kwargs(raw_label_repo=noop),
    )
    v3_base = tmp_path / "v3_uploads"
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "p.jpg").write_bytes(b"x")

    spy_state = MagicMock(wraps=executor._state)
    spy_runner = MagicMock()
    ac = AnalysisContext(primary_evidence=[], visual_references=[], instructions=[])
    spy_runner.build_analysis_context.return_value = ac
    spy_runner.build_pipeline_input.return_value = (
        JobInput(
            video_path="",
            mode="hybrid",
            input_type="photos",
            metadata={"analysis_context": analysis_context_to_dict(ac)},
        ),
        "",
    )
    spy_runner.run_hybrid_pipeline.return_value = PipelineRunResult(2, None)

    executor._state = spy_state
    executor._preparation_service._state = spy_state
    executor._monitoring_service._state = spy_state
    executor._pipeline_runner = spy_runner

    class _FakePipeline:
        def process_video(self, *args: object, **kwargs: object) -> PipelineRunResult:
            raise AssertionError("delegated to runner")

    with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as ms:
        ms.return_value.output_dir = str(tmp_path)
        ms.return_value.artifact_storage_legacy_local_read_enabled = True
        with patch(
            "src.infrastructure.pipeline.v3_job_executor.HybridInventoryPipeline",
            return_value=_FakePipeline(),
        ):
            assert executor.execute(tmp_path, job_id) is True

    spy_state.fail_job_and_aisle.assert_called_once()
    call_kw = spy_state.fail_job_and_aisle.call_args[0]
    assert call_kw[0] == job_id
    assert "code 2" in call_kw[2]
