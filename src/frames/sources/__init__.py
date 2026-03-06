"""FrameSource implementations: video, photos."""

from src.frames.sources.base import FrameSource
from src.frames.sources.factory import get_frame_source
from src.frames.sources.photos_source import PhotosFrameSource
from src.frames.sources.video_source import VideoFrameSource

__all__ = ["FrameSource", "VideoFrameSource", "PhotosFrameSource", "get_frame_source"]
