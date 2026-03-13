"""
Unit tests for v2.3.A pipeline components: RunContext, PipelineStage, InputPreparationStage.

These tests validate Stage A extraction without running the full pipeline.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.jobs.models import JobInput
from src.pipeline.context.run_context import RunContext
from src.pipeline.stages.input_preparation_stage import InputPreparationStage, PreparedInput


def test_run_context_creation() -> None:
    """RunContext can be created with required fields and optional metadata."""
    settings = MagicMock()
    logger = MagicMock()
    job_input = JobInput(video_path="/x/v.mp4", mode="hybrid", input_type="video")
    ctx = RunContext(
        job_id="job1",
        run_id="run1",
        workspace_path=Path("/out"),
        run_dir=Path("/out/job1/run1"),
        job_input=job_input,
        settings=settings,
        logger=logger,
    )
    assert ctx.job_id == "job1"
    assert ctx.run_id == "run1"
    assert ctx.run_dir == Path("/out/job1/run1")
    assert ctx.job_input.input_type == "video"
    assert ctx.metadata == {}


def test_input_preparation_stage_video_returns_prepared_input(tmp_path: Path) -> None:
    """InputPreparationStage.run with video input creates run_dir and returns PreparedInput."""
    run_dir = tmp_path / "job1" / "run1"
    settings = MagicMock()
    job_input = JobInput(video_path="/dummy/v.mp4", mode="hybrid", input_type="video")
    context = RunContext(
        job_id="job1",
        run_id="run1",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    stage = InputPreparationStage()
    result = stage.run(context, None)
    assert isinstance(result, PreparedInput)
    assert result.job_id == "job1"
    assert result.input_type == "video"
    assert result.job_input is job_input
    assert context.run_dir == run_dir
    assert run_dir.exists()
    assert run_dir.is_dir()


def test_input_preparation_stage_photos_normalization_fails_without_manifest(tmp_path: Path) -> None:
    """InputPreparationStage with photos input_type raises when manifest is missing."""
    run_dir = tmp_path / "job2" / "run1"
    run_dir.mkdir(parents=True)
    # No input_manifest.json
    settings = MagicMock()
    job_input = JobInput(
        video_path="",
        mode="hybrid",
        input_type="photos",
        input_manifest_path="run1/input_manifest.json",
        photos_dir="run1/input_photos",
    )
    context = RunContext(
        job_id="job2",
        run_id="run1",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    stage = InputPreparationStage()
    with pytest.raises(FileNotFoundError):
        stage.run(context, None)
