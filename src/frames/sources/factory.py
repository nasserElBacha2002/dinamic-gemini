"""Stage 2.2.B — FrameSource factory."""

from src.frames.sources.photos_source import PhotosFrameSource
from src.frames.sources.video_source import VideoFrameSource


def get_frame_source(input_type: str):
    """Return the FrameSource implementation for the given input_type.

    - "video" -> VideoFrameSource()
    - "photos" -> PhotosFrameSource()

    Raises:
        ValueError: if input_type is not "video" or "photos".
    """
    normalized = (input_type or "video").strip().lower()
    if normalized == "video":
        return VideoFrameSource()
    if normalized == "photos":
        return PhotosFrameSource()
    raise ValueError(f"unknown input_type: {input_type!r} (expected 'video' or 'photos')")
