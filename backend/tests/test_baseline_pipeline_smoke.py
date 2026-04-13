"""
Baseline pipeline smoke test for v2.3.A.

Runs the hybrid pipeline end-to-end with minimal valid input (patched LLM executor + stub frames).
Serves as a regression guard during Stage A refactors: must remain green before and after
RunContext, PipelineStage, and InputPreparationStage extraction.

Backlog: Baseline Pipeline Smoke Test (prerequisite for stage extraction).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.jobs.models import JobInput
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline, PipelineRunResult

# Reuse fixture from E2E tests
FIXTURES_V21 = Path(__file__).resolve().parent / "fixtures" / "v2_1"
GLOBAL_ANALYSIS_OK = FIXTURES_V21 / "global_analysis_ok.json"


def _make_offline_pipeline_settings() -> MagicMock:
    """Minimal settings when hybrid LLM resolution is patched (no network)."""
    s = MagicMock()
    s.llm_provider = "openai"
    s.gemini_api_key = ""
    s.openai_api_key = "offline-test-key"
    s.photo_resize_max_side = 1280
    s.photo_jpeg_quality = 85
    s.photos_min_side = 64
    s.debug_save_frames = False
    s.hybrid_max_frames = None
    return s


def _run_pipeline_sync(
    output_dir: Path, job_id: str, run_id: str, settings: MagicMock, job_input: JobInput
) -> PipelineRunResult:
    """Run hybrid pipeline synchronously; return PipelineRunResult. Uses public process_video API."""
    pipeline = HybridInventoryPipeline()
    logger = MagicMock()
    video_path = job_input.video_path or ""
    return pipeline.process_video(
        video_path,
        mode="hybrid",
        settings=settings,
        video_id=job_id,
        output_path=output_dir,
        run_id=run_id,
        logger=logger,
        job_input=job_input,
    )


def test_baseline_pipeline_smoke_minimal_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Baseline smoke test: pipeline runs with minimal input and produces valid report.

    - Runs pipeline with stub frames and patched registry executor (no network).
    - Asserts exit code 0.
    - Asserts hybrid_report.json exists.
    - Asserts report has required top-level keys: report_version, mode, entities.
    - Does not assert entity count or content; only structure.

    This test must pass before and after all Stage A refactors (RunContext,
    PipelineStage, InputPreparationStage, minimal pipeline integration).
    """
    from tests.support.llm_executor_harness import patch_offline_hybrid_json_fixture

    patch_offline_hybrid_json_fixture(monkeypatch, GLOBAL_ANALYSIS_OK)

    job_id = "baseline_smoke_01"
    run_id = "run"
    run_dir = tmp_path / job_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Stub frame extraction: a few frame images under run_dir
    extract_dir = run_dir / ".frames_extract_stub"
    extract_dir.mkdir(exist_ok=True)
    for i in range(2):
        p = extract_dir / f"frame_{i:06d}.jpg"
        cv2.imwrite(str(p), np.zeros((64, 64, 3), dtype=np.uint8))

    from src.frames.types import FramesBundle

    bundle = FramesBundle(
        frames=sorted(extract_dir.glob("*.jpg")),
        frame_refs=["frame_000000", "frame_000001"],
        metadata={
            "source": "video",
            "frame_count": 2,
            "selected_by": "video_sampling",
            "frame_indices": [0, 1],
        },
    )

    settings = _make_offline_pipeline_settings()
    job_input = JobInput(video_path="/dummy/video.mp4", mode="hybrid", input_type="video")

    with patch("src.pipeline.stages.frame_acquisition_stage.get_frame_source") as mock_src:
        mock_source = MagicMock()
        mock_source.get_frames.return_value = bundle
        mock_src.return_value = mock_source

        result = _run_pipeline_sync(tmp_path, job_id, run_id, settings=settings, job_input=job_input)

    assert result.exit_code == 0, "Pipeline must complete successfully (exit code 0)"

    report_path = run_dir / "hybrid_report.json"
    assert report_path.exists(), "hybrid_report.json must exist after run"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "report_version" in report, "Report must contain report_version"
    assert "mode" in report, "Report must contain mode"
    assert "entities" in report, "Report must contain entities"
    assert isinstance(report["entities"], list), "entities must be a list"

    # Minimal structure check; do not depend on exact entity count
    assert report.get("report_version") == "2.1"
    assert report.get("mode") == "hybrid_v2.1"

    # Phase 5: run_metadata propagated in memory with visual_reference_context (no refs in this run)
    assert result.run_metadata is not None, "run_metadata must be set on success"
    assert "visual_reference_context" in result.run_metadata
    vrc = result.run_metadata["visual_reference_context"]
    assert vrc["resolved"] is False
    assert vrc["reference_ids"] == []
    assert vrc["resolved_count"] == 0
    assert vrc["provider_consumed"] is False
    assert vrc["provider_consumed_count"] == 0
    # Phase 7: provider key present in run_metadata (value may be None if provider not reported)
    assert "provider" in result.run_metadata
    if result.run_metadata["provider"] is not None:
        assert isinstance(result.run_metadata["provider"], str)
