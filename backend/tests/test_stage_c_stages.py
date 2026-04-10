"""
Stage 2.3.C — Unit tests for extracted pipeline stages.

Focused tests for FrameAcquisitionStage, AnalysisStage, EntityResolutionStage, ReportingStage.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.domain.entity import Entity
from src.pipeline.context.run_context import RunContext
from src.pipeline.stages.frame_acquisition_stage import FrameAcquisitionStage, AcquiredFrames
from src.pipeline.ports.analysis_provider import AnalysisResult
from src.pipeline.stages.analysis_stage import AnalysisStage, AnalysisStageResult
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage, ResolvedEntities
from src.pipeline.stages.reporting_stage import ReportingStage, ReportingStageInput, ReportingResult
from src.pipeline.stages.input_preparation_stage import PreparedInput
from src.jobs.models import JobInput
from src.frames.types import FramesBundle


def test_frame_acquisition_stage_returns_acquired_frames(tmp_path: Path) -> None:
    """FrameAcquisitionStage with mocked FrameSource returns AcquiredFrames with expected shape."""
    run_dir = tmp_path / "job1" / "run1"
    run_dir.mkdir(parents=True)
    # Write one frame so cv2.imread can load it
    frame_path = run_dir / "f0.jpg"
    cv2.imwrite(str(frame_path), np.zeros((64, 64, 3), dtype=np.uint8))

    bundle = FramesBundle(
        frames=[frame_path],
        frame_refs=["frame_0"],
        metadata={"source": "video", "frame_count": 1, "frame_indices": [0]},
    )
    job_input = JobInput(video_path="/dummy/v.mp4", mode="hybrid", input_type="video")
    prepared = PreparedInput(job_id="job1", input_type="video", job_input=job_input)
    context = RunContext(
        job_id="job1",
        run_id="run1",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=MagicMock(hybrid_max_frames=None),
        logger=MagicMock(),
    )

    with patch("src.pipeline.stages.frame_acquisition_stage.get_frame_source") as mock_src:
        mock_source = MagicMock()
        mock_source.get_frames.return_value = bundle
        mock_src.return_value = mock_source

        stage = FrameAcquisitionStage()
        result = stage.run(context, prepared)

    assert isinstance(result, AcquiredFrames)
    assert len(result.frames_nd) == 1
    assert result.frames_nd[0].shape == (64, 64, 3)
    assert result.frame_paths == [frame_path]
    assert result.metadata.get("frame_count") == 1
    assert result.frame_refs == ["frame_0"]


def test_frame_acquisition_stage_alignment_when_one_frame_fails_to_load(tmp_path: Path) -> None:
    """When one candidate frame fails to load, returned collections stay positionally aligned."""
    run_dir = tmp_path / "job1" / "run1"
    run_dir.mkdir(parents=True)
    ok1 = run_dir / "f0.jpg"
    ok2 = run_dir / "f2.jpg"
    cv2.imwrite(str(ok1), np.zeros((64, 64, 3), dtype=np.uint8))
    cv2.imwrite(str(ok2), np.zeros((64, 64, 3), dtype=np.uint8))
    # Middle path does not exist or is unreadable
    bad_path = run_dir / "f1_missing.jpg"
    bundle = FramesBundle(
        frames=[ok1, bad_path, ok2],
        frame_refs=["ref0", "ref1", "ref2"],
        metadata={"source": "video", "frame_count": 3, "frame_indices": [0, 1, 2]},
    )
    job_input = JobInput(video_path="/dummy/v.mp4", mode="hybrid", input_type="video")
    prepared = PreparedInput(job_id="job1", input_type="video", job_input=job_input)
    context = RunContext(
        job_id="job1",
        run_id="run1",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=MagicMock(hybrid_max_frames=None),
        logger=MagicMock(),
    )
    with patch("src.pipeline.stages.frame_acquisition_stage.get_frame_source") as mock_src:
        mock_source = MagicMock()
        mock_source.get_frames.return_value = bundle
        mock_src.return_value = mock_source
        stage = FrameAcquisitionStage()
        result = stage.run(context, prepared)

    n = len(result.frames_nd)
    assert n == 2, "Only two frames should load"
    assert len(result.frame_paths) == n
    assert len(result.frame_refs) == n
    assert len(result.metadata["frame_indices"]) == n
    assert result.frame_paths == [ok1, ok2]
    assert result.frame_refs == ["ref0", "ref2"]
    assert result.metadata["frame_indices"] == [0, 2]


def test_frame_acquisition_stage_raises_when_no_frames_load(tmp_path: Path) -> None:
    """FrameAcquisitionStage raises when bundle has paths but cv2.imread returns None for all."""
    run_dir = tmp_path / "job1" / "run1"
    run_dir.mkdir(parents=True)
    # Path that does not exist or is not a valid image
    bad_path = run_dir / "nonexistent.jpg"
    bundle = FramesBundle(
        frames=[bad_path],
        frame_refs=["frame_0"],
        metadata={"source": "video", "frame_count": 1},
    )
    job_input = JobInput(video_path="/dummy/v.mp4", mode="hybrid", input_type="video")
    prepared = PreparedInput(job_id="job1", input_type="video", job_input=job_input)
    context = RunContext(
        job_id="job1",
        run_id="run1",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=MagicMock(hybrid_max_frames=None),
        logger=MagicMock(),
    )

    with patch("src.pipeline.stages.frame_acquisition_stage.get_frame_source") as mock_src:
        mock_source = MagicMock()
        mock_source.get_frames.return_value = bundle
        mock_src.return_value = mock_source

        stage = FrameAcquisitionStage()
        with pytest.raises(ValueError, match="No frames could be loaded"):
            stage.run(context, prepared)


def test_analysis_stage_delegates_to_provider() -> None:
    """AnalysisStage calls AnalysisProvider.analyze and returns AnalysisStageResult."""
    context = MagicMock(spec=RunContext)
    context.job_id = "j1"
    context.run_dir = Path("/tmp")
    acquired = AcquiredFrames(
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        metadata={"frame_count": 1},
        frame_refs=["f0"],
    )
    mock_provider = MagicMock()
    mock_provider.analyze.return_value = AnalysisResult(
        parsed_json={"total_entities_detected": 0, "entities": []},
        provider_name="gemini",
        provider_metadata=None,
    )

    stage = AnalysisStage(mock_provider)
    result = stage.run(context, acquired)

    assert isinstance(result, AnalysisStageResult)
    assert result.parsed_json == {"total_entities_detected": 0, "entities": []}
    assert result.provider_name == "gemini"
    mock_provider.analyze.assert_called_once()
    call_kw = mock_provider.analyze.call_args
    assert call_kw[0][0] is context
    assert len(call_kw[0][1]) == 1  # frames_nd
    assert call_kw[0][2] == acquired.frame_paths
    assert call_kw[0][3] == acquired.frame_refs
    assert call_kw[0][4] == acquired.metadata


def test_entity_resolution_stage_parses_and_resolves() -> None:
    """EntityResolutionStage parses v2.1 JSON and runs sort/resolve/status/quality."""
    context = MagicMock(spec=RunContext)
    context.job_id = "j1"
    context.logger = MagicMock()
    analysis_result = AnalysisStageResult(
        parsed_json={
            "total_entities_detected": 1,
            "entities": [
                {
                    "model_entity_id": "e1",
                    "entity_type": "PALLET",
                    "confidence": 0.9,
                },
            ],
        },
        provider_name="gemini",
    )

    stage = EntityResolutionStage()
    result = stage.run(context, analysis_result)

    assert isinstance(result, ResolvedEntities)
    assert len(result.entities) == 1
    assert result.entities[0].entity_type == "PALLET"
    assert result.entities[0].model_entity_id == "e1"
    assert result.entities[0].count_status is not None
    assert result.entities[0].entity_quality_score >= 0


def test_reporting_stage_writes_hybrid_report(tmp_path: Path) -> None:
    """ReportingStage builds report and writes hybrid_report.json to run_dir."""
    run_dir = tmp_path / "job1" / "run1"
    run_dir.mkdir(parents=True)
    context = MagicMock(spec=RunContext)
    context.run_dir = run_dir
    context.logger = MagicMock()

    entity = Entity(
        entity_uid="j1_e1",
        entity_type="PALLET",
        model_entity_id="e1",
        count_status="COUNTED",
        final_quantity=1,
        entity_quality_score=0.9,
    )
    reporting_input = ReportingStageInput(
        entities=[entity],
        frames_count=1,
        frame_indices=[0],
        video_path_for_report="/dummy/v.mp4",
    )

    stage = ReportingStage()
    result = stage.run(context, reporting_input)

    assert isinstance(result, ReportingResult)
    assert result.report_path == run_dir / "hybrid_report.json"
    assert result.report_path.exists()
    assert "report_version" in result.report
    assert result.report["report_version"] == "2.1"
    assert "entities" in result.report
    assert len(result.report["entities"]) == 1


def test_orchestrator_returns_1_on_stage_failure() -> None:
    """When a stage raises, orchestrator logs and returns exit code 1."""
    from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

    pipeline = HybridInventoryPipeline()
    logger = MagicMock()
    with patch.object(pipeline, "_input_stage") as mock_input:
        mock_input.run.side_effect = ValueError("input validation failed")
        result = pipeline._run_hybrid(
            "/dummy/v.mp4",
            settings=MagicMock(),
            video_id="j1",
            output_path=Path("/tmp"),
            run_id="r1",
            logger=logger,
        )
    assert result.exit_code == 1
    logger.exception.assert_called()
    call_args = logger.exception.call_args[0]
    assert call_args[0] == "Stage failure: %s (job_id=%s): %s"
    assert call_args[1] == "InputPreparationStage"
    assert call_args[2] == "j1"
