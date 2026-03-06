"""Stage 2.2.B — VideoFrameSource: frames from video file (v2.1 behavior).

Writes to run_dir/.frames_extract (transient) so the pipeline can load from paths.
Only the pipeline writes run_dir/frames_sent when debug_save_frames is enabled.
"""

import uuid
from pathlib import Path

import cv2

from src.config import load_settings
from src.frames.types import FramesBundle
from src.jobs.models import JobInput
from src.video.frames import STRATEGY_OPTIMIZED, extract_representative_frames

# Safe default cap when hybrid_max_frames is None (avoid loading too many frames into RAM)
_HYBRID_MAX_FRAMES_DEFAULT = 10000


class VideoFrameSource:
    """Obtain frames from a video file via existing extract_representative_frames.

    Does NOT write to run_dir/frames_sent (pipeline does that only when debug_save_frames).
    Writes to run_dir/.frames_extract_<uuid> so frames are available as paths.
    """

    def get_frames(
        self,
        job_id: str,
        run_dir: Path,
        job_input: JobInput,
    ) -> FramesBundle:
        """Extract representative frames; persist to run_dir/.frames_extract_* (not frames_sent). Return bundle."""
        video_path = (job_input.video_path or "").strip()
        if not video_path:
            raise ValueError("video_path is required for video frame source")
        settings = load_settings()
        max_frames = getattr(settings, "hybrid_max_frames", None) or _HYBRID_MAX_FRAMES_DEFAULT
        frames_nd, meta = extract_representative_frames(
            video_path,
            max_frames=max_frames,
            strategy=STRATEGY_OPTIMIZED,
        )
        if not frames_nd:
            return FramesBundle(
                frames=[],
                frame_refs=[],
                metadata={
                    "source": "video",
                    "frame_count": 0,
                    "selected_by": "video_sampling",
                    **meta,
                },
            )
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        # Transient dir so only pipeline writes frames_sent when debug_save_frames
        extract_dir = run_dir / f".frames_extract_{uuid.uuid4().hex[:12]}"
        extract_dir.mkdir(exist_ok=True)
        frame_indices = meta.get("frame_indices") or list(range(len(frames_nd)))
        paths: list[Path] = []
        frame_refs: list[str] = []
        for i, (frame, idx) in enumerate(zip(frames_nd, frame_indices)):
            path = extract_dir / f"frame_{idx:06d}.jpg"
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85]):
                path = extract_dir / f"frame_{i:06d}.jpg"
                cv2.imwrite(str(path), frame)
            paths.append(path)
            frame_refs.append(f"frame_{idx:06d}")
        metadata = {
            "source": "video",
            "frame_count": len(paths),
            "selected_by": "video_sampling",
            **meta,
        }
        return FramesBundle(frames=paths, frame_refs=frame_refs, metadata=metadata)
