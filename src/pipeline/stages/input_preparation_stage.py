"""
InputPreparationStage — validate input, prepare run dir and paths (v2.3.A).

This stage has three responsibilities (kept together for Stage A; may be split later):

1. Directory creation: ensure the canonical run directory (context.run_dir) exists.
   RunContext owns the canonical run_dir; this stage only creates it.

2. Input validation: ensure job_input and input_type are available from context.

3. Photo normalization: when input_type is "photos", resolve manifest/photos paths
   and run normalize_photos_for_job so downstream stages consume normalized images.
   Photo normalization is currently handled here for Stage A but may be extracted
   to a dedicated step or stage in a later refactor.

Returns PreparedInput (job_id, input_type, job_input) for the next stage.
The pipeline must use context.run_dir as the canonical run directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.frames.normalize import normalize_photos_for_job, validate_relative_path
from src.jobs.models import JobInput
from src.pipeline.context.run_context import RunContext


@dataclass
class PreparedInput:
    """Output of InputPreparationStage; input for FrameAcquisitionStage. run_dir is owned by RunContext."""

    job_id: str
    input_type: str
    job_input: JobInput


class InputPreparationStage:
    """Stage: validate input type, prepare run directory and (for photos) normalize inputs."""

    def run(self, context: RunContext, data: None) -> PreparedInput:
        """
        Create run directory and optionally run photo normalization.

        Responsibilities: (1) ensure context.run_dir exists; (2) validate input from context;
        (3) for photos, resolve paths and call normalize_photos_for_job (may be extracted later).

        Args:
            context: Run context with job_id, run_id, run_dir, job_input, settings, logger.
            data: Ignored (first stage); may be None.

        Returns:
            PreparedInput with job_id, input_type, job_input. Use context.run_dir for paths.

        Raises:
            FileNotFoundError, ValueError: From photo normalization if input_type is photos.
        """
        run_dir = context.run_dir
        run_dir.mkdir(parents=True, exist_ok=True)

        job_input = context.job_input
        input_type = getattr(job_input, "input_type", "video") or "video"

        if input_type == "photos":
            try:
                raw_manifest = (getattr(job_input, "input_manifest_path", None) or "").strip()
                raw_photos = (getattr(job_input, "photos_dir", None) or "").strip()
                # Workspace layout: output_path / job_id / run_id (run_dir). Job inputs may be
                # stored under run_dir (e.g. run_dir/input_manifest.json) or as relative paths
                # under run_dir.parent (job-level dir). run_dir.parent is the job workspace.
                if raw_manifest:
                    manifest_rel = validate_relative_path(raw_manifest, "input_manifest_path")
                    manifest_path = run_dir.parent / manifest_rel  # relative to job dir
                else:
                    manifest_path = run_dir / "input_manifest.json"
                if raw_photos:
                    photos_rel = validate_relative_path(raw_photos, "photos_dir")
                    photos_dir = run_dir.parent / photos_rel  # relative to job dir
                else:
                    photos_dir = run_dir / "input_photos"
                normalized_dir = run_dir / "input_photos_normalized"
                normalize_photos_for_job(
                    run_dir,
                    context.settings,
                    manifest_path=manifest_path,
                    photos_dir=photos_dir,
                    normalized_dir=normalized_dir,
                )
            except (FileNotFoundError, ValueError) as e:
                context.logger.exception("Photo normalization failed: %s", e)
                raise

        return PreparedInput(
            job_id=context.job_id,
            input_type=input_type,
            job_input=job_input,
        )
