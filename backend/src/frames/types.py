"""Stage 2.2.B — FramesBundle: unified frame container for pipeline."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FramesBundle(BaseModel):
    """Container of frame paths and metadata for the hybrid pipeline.

    - frames: paths to images on disk (List[Path])
    - frame_refs: human-readable references (e.g. frame_0001, photo_0001)
    - metadata: source, frame_count, selected_by, and optional extras (fps, frame_indices for video)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    frames: list[Path] = Field(default_factory=list, description="Paths to image files.")
    frame_refs: list[str] = Field(
        default_factory=list, description="Human-readable refs (frame_0001, photo_0001)."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="source, frame_count, selected_by, etc."
    )
