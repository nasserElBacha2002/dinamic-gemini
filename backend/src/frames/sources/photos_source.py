"""Stage 2.2.B — PhotosFrameSource: frames from input_manifest.json (uploaded photos).
Stage 2.2.C — Prefer normalized paths (input_photos_normalized/) when present.

Uses job_input.input_manifest_path and job_input.photos_dir when provided;
fallback: run_dir/input_manifest.json and run_dir/input_photos/.
When manifest has stored_normalized_filename for all photos and normalized dir exists,
returns paths from run_dir/input_photos_normalized/.
"""

import json
import logging
from pathlib import Path

from src.frames.normalize import photos_use_normalized
from src.frames.types import FramesBundle
from src.jobs.models import JobInput
from src.jobs.photos_paths import resolve_manifest_path, resolve_photos_dir

logger = logging.getLogger(__name__)


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
        manifest_path = resolve_manifest_path(run_dir, job_input)
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
        photos_dir = resolve_photos_dir(run_dir, job_input)
        if not photos_dir.is_dir():
            raise FileNotFoundError(
                f"photos directory not found: {photos_dir} (missing input_photos/)"
            )
        # Stage 2.2.C: prefer normalized paths when present (all entries have stored_normalized_filename and files exist)
        use_normalized = photos_use_normalized(run_dir, manifest)
        if use_normalized:
            normalized_dir = run_dir / "input_photos_normalized"
            photos_dir = normalized_dir
        frames: list[Path] = []
        frame_refs: list[str] = []
        for position_1based, entry in enumerate(
            sorted(photos_list, key=lambda x: x.get("index", 0)), start=1
        ):
            if use_normalized:
                stored = (
                    entry.get("stored_normalized_filename") or entry.get("stored_filename") or ""
                )
            else:
                stored = entry.get("stored_filename") or ""
            if not stored:
                raise ValueError("manifest photo entry missing stored_filename")
            path = photos_dir / stored
            if not path.is_file():
                raise FileNotFoundError(
                    f"missing input photo: {path} (listed in input_manifest.json)"
                )
            frames.append(path)
            # Epic 3.1.A: use image_id as frame_ref when present; else 1-based fallback (no 0-based leakage)
            image_id = entry.get("image_id") if isinstance(entry.get("image_id"), str) else None
            frame_ref = (
                (image_id.strip() or f"photo_{position_1based:04d}")
                if image_id
                else f"photo_{position_1based:04d}"
            )
            frame_refs.append(frame_ref)
        metadata = {
            "source": "photos",
            "frame_count": len(frames),
            "selected_by": "uploaded_photos",
        }
        return FramesBundle(frames=frames, frame_refs=frame_refs, metadata=metadata)
