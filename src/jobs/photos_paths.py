"""
Public helpers for resolving photos-job paths (manifest and photos directory).

Intended for cross-layer use: pipeline stages (e.g. entity resolution, reporting),
frame sources, and any code that needs to locate the input manifest or photos dir
for a job run without depending on private helpers from the frames layer.

Epic 5 corrections: this module provides the single public contract for manifest/
photos path resolution so ReportingStage and EntityResolutionStage do not depend
on private functions from src.frames.sources.photos_source.
"""

from __future__ import annotations

from pathlib import Path

from src.jobs.models import JobInput
from src.utils.validation import validate_relative_path


def resolve_manifest_path(run_dir: Path, job_input: JobInput) -> Path:
    """Resolve the path to input_manifest.json for a photos job.

    Uses job_input.input_manifest_path (relative to job dir) when set;
    otherwise returns run_dir / "input_manifest.json".

    Args:
        run_dir: The run directory (e.g. job_dir/run).
        job_input: Job input model with optional input_manifest_path, photos_dir.

    Returns:
        Absolute path to the manifest file. Caller should check exists() before reading.
    """
    run_dir = Path(run_dir)
    raw = (job_input.input_manifest_path or "").strip()
    if raw:
        safe = validate_relative_path(raw, "input_manifest_path")
        return run_dir.parent / safe
    return run_dir / "input_manifest.json"


def resolve_photos_dir(run_dir: Path, job_input: JobInput) -> Path:
    """Resolve the path to the photos directory for a photos job.

    Uses job_input.photos_dir (relative to job dir) when set;
    otherwise returns run_dir / "input_photos".

    Args:
        run_dir: The run directory (e.g. job_dir/run).
        job_input: Job input model with optional photos_dir.

    Returns:
        Absolute path to the photos directory.
    """
    run_dir = Path(run_dir)
    raw = (job_input.photos_dir or "").strip()
    if raw:
        safe = validate_relative_path(raw, "photos_dir")
        return run_dir.parent / safe
    return run_dir / "input_photos"


def photos_dir_relative_for_manifest(job_input: JobInput) -> str:
    """Return the relative photos-dir string used when loading image metadata from the manifest.

    This is the value passed to load_job_images_from_manifest(manifest_path, photos_dir_rel)
    for storage_path construction. Default is "run/input_photos" when job_input.photos_dir is unset.

    Args:
        job_input: Job input model with optional photos_dir.

    Returns:
        Relative path string (e.g. "run/input_photos").
    """
    raw = (job_input.photos_dir or "").strip()
    return raw if raw else "run/input_photos"
