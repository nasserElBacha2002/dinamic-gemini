"""Stage 2.2.B — FrameSource strategy: video and photos input."""

from src.frames.sources.factory import get_frame_source
from src.frames.types import FramesBundle

__all__ = ["FramesBundle", "get_frame_source"]
