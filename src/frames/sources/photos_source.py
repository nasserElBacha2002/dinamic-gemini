"""Stage 2.2.B — PhotosFrameSource: frames from input_manifest.json (uploaded photos).

Uses job_input.input_manifest_path and job_input.photos_dir when provided;
fallback: run_dir/input_manifest.json and run_dir/input_photos/.
"""

import json
import logging
from pathlib import Path

from src.frames.types import FramesBundle
from src.jobs.models import JobInput

logger = logging.getLogger(__name__)


def _resolve_manifest_path(run_dir: Path, job_input: JobInput) -> Path:
    """Manifest path: job_input.input_manifest_path (relative to job_dir) or run_dir/input_manifest.json."""
    run_dir = Path(run_dir)
    if job_input.input_manifest_path and str(job_input.input_manifest_path).strip():
        return run_dir.parent / job_input.input_manifest_path.strip()
    return run_dir / "input_manifest.json"


def _resolve_photos_dir(run_dir: Path, job_input: JobInput) -> Path:
    """Photos dir: job_input.photos_dir (relative to job_dir) or run_dir/input_photos."""
    run_dir = Path(run_dir)
    if job_input.photos_dir and str(job_input.photos_dir).strip():
        return run_dir.parent / job_input.photos_dir.strip()
    return run_dir / "input_photos"


class PhotosFrameSource:
    """Obtain frames from uploaded photos via input_manifest.json (Stage 2.2.A)."""

    def get_frames(
        self,
        job_id: str,
        run_dir: Path,
        job_input: JobInput,
    ) -> FramesBundle:
        """Read manifest (from job_input or run_dir), resolve photo paths, return bundle in index order."""
        run_dir = Path(run_dir)
        manifest_path = _resolve_manifest_path(run_dir, job_input)
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"photos input manifest not found: {manifest_path} (missing input_manifest.json)"
            )
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"invalid or unreadable input_manifest.json: {e}") from e
        if manifest.get("input_type") != "photos":
            raise ValueError(f"manifest input_type is not 'photos': {manifest.get('input_type')}")
        photos_list = manifest.get("photos") or []
        if not photos_list:
            return FramesBundle(
                frames=[],
                frame_refs=[],
                metadata={"source": "photos", "frame_count": 0, "selected_by": "uploaded_photos"},
            )
        photos_dir = _resolve_photos_dir(run_dir, job_input)
        if not photos_dir.is_dir():
            raise FileNotFoundError(
                f"photos directory not found: {photos_dir} (missing input_photos/)"
            )
        frames: list[Path] = []
        frame_refs: list[str] = []
        for entry in sorted(photos_list, key=lambda x: x.get("index", 0)):
            stored = entry.get("stored_filename") or ""
            if not stored:
                raise ValueError("manifest photo entry missing stored_filename")
            path = photos_dir / stored
            if not path.is_file():
                raise FileNotFoundError(
                    f"missing input photo: {path} (listed in input_manifest.json)"
                )
            frames.append(path)
            idx = entry.get("index", len(frames))
            frame_refs.append(f"photo_{idx:04d}")
        metadata = {
            "source": "photos",
            "frame_count": len(frames),
            "selected_by": "uploaded_photos",
        }
        return FramesBundle(frames=frames, frame_refs=frame_refs, metadata=metadata)
