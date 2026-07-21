"""Regression: GLOBAL_BATCH run_id / run_dir / report path must stay aligned."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.application.services.image_processing.global_fallback_batching import (
    GlobalFallbackBatchSlice,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.global_fallback_hybrid_runner import (
    HybridGlobalFallbackBatchAnalyzer,
)
from src.infrastructure.pipeline.v3_pipeline_execution_service import (
    V3PipelineExecutionResult,
)
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import AnalysisContext
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult


def test_analyze_batch_aligns_pipeline_run_id_with_run_dir(tmp_path: Path) -> None:
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "job-gf"
    aisle_id = "aisle-1"
    asset_id = "asset-1"
    job_dir = tmp_path / "output" / job_id
    job_dir.mkdir(parents=True)

    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
        execution_id="ex-1",
        provider_name="claude",
        model_name="claude-opus-4-7",
    )
    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    asset = SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="a.jpg",
        storage_path="a.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )
    batch = GlobalFallbackBatchSlice(
        batch_index=0,
        batch_count=1,
        ordered_asset_ids=(asset_id,),
        fingerprint="fp",
    )
    snapshot = SimpleNamespace(
        provider="claude",
        model="claude-opus-4-7",
        supplier_prompt={"content": "supplier text", "prompt_id": "p1", "prompt_version": 1},
    )

    pipeline_runner = MagicMock()
    pipeline_runner.build_analysis_context.return_value = AnalysisContext(
        primary_evidence=[],
        visual_references=[],
        instructions=[],
    )
    job_input = JobInput(
        video_path="",
        mode="hybrid",
        input_type="photos",
        metadata={},
    )
    pipeline_runner.build_pipeline_input.return_value = (job_input, "")

    captured: dict[str, object] = {}

    def _run(req):  # type: ignore[no-untyped-def]
        captured["run_dir"] = req.run_dir
        captured["pipeline_run_id"] = req.pipeline_run_id
        report_path = req.run_dir / "hybrid_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            '{"entities":[{"model_entity_id":"E1"}],"schema_version":"v2.1"}',
            encoding="utf-8",
        )
        return V3PipelineExecutionResult(
            report={"entities": [{"model_entity_id": "E1"}], "schema_version": "v2.1"},
            pipeline_result=PipelineRunResult(0, {}),
            report_path=report_path,
        )

    exec_svc = MagicMock()
    exec_svc.run.side_effect = _run

    inventory_repo = MagicMock()
    inventory_repo.get_by_id.return_value = SimpleNamespace(client_id="c1")

    analyzer = HybridGlobalFallbackBatchAnalyzer(
        pipeline_execution_service=exec_svc,
        pipeline_runner=pipeline_runner,
        settings=MagicMock(),
        base_path=tmp_path / "output",
        v3_base=tmp_path / "v3",
        job_dir=job_dir,
        run_dir=job_dir / "run",
        inventory_repo=inventory_repo,
        log=logging.getLogger("gf-test"),
        execution_observer=MagicMock(),
        cancellation_checkpoint=MagicMock(),
    )

    result = analyzer.analyze_batch(
        job=job,
        aisle=aisle,
        assets=[asset],
        batch=batch,
        snapshot=snapshot,
        prompt_fingerprint="ph",
    )

    assert result.ok is True
    expected_segment = "global_fallback_batch_0"
    build_kwargs = pipeline_runner.build_pipeline_input.call_args.kwargs
    assert build_kwargs["run_id"] == expected_segment
    assert captured["pipeline_run_id"] == expected_segment
    assert captured["run_dir"] == job_dir / expected_segment
    assert (job_dir / expected_segment).is_dir()
