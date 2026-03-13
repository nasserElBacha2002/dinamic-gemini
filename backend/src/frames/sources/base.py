"""Stage 2.2.B — FrameSource protocol."""

from pathlib import Path
from typing import Protocol

from src.frames.types import FramesBundle
from src.jobs.models import JobInput


class FrameSource(Protocol):
    """Protocol for obtaining frames (video or photos) for the hybrid pipeline."""

    def get_frames(
        self,
        job_id: str,
        run_dir: Path,
        job_input: JobInput,
    ) -> FramesBundle:
        """Return a FramesBundle with frame paths and metadata.

        Args:
            job_id: Job identifier.
            run_dir: Job run directory (e.g. output/<job_id>/run).
            job_input: Job input (video_path, input_type, input_manifest_path, photos_dir, etc.).

        Returns:
            FramesBundle with frames (paths), frame_refs, metadata.

        Raises:
            RuntimeError, ValueError, FileNotFoundError: on missing/invalid input.
        """
        ...
