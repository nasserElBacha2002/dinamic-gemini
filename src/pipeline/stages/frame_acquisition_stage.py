"""
FrameAcquisitionStage — obtain frames from FrameSource and load into memory (v2.3.C).

Uses current get_frame_source + get_frames logic; applies same max-load cap and validation.
Returns only successfully loaded frames; all output collections are positionally aligned.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from src.frames.sources.factory import get_frame_source
from src.pipeline.stages.input_preparation_stage import PreparedInput
from src.pipeline.context.run_context import RunContext

# Hard cap when settings.hybrid_max_frames is unset (single source of truth for load cap)
HYBRID_MAX_FRAMES_LOAD_CAP = 48


@dataclass
class AcquiredFrames:
    """Output of FrameAcquisitionStage: frames in memory and metadata for analysis. All lists are positionally aligned."""

    frames_nd: List[np.ndarray]
    frame_paths: List[Path]
    metadata: dict
    frame_refs: List[str]


class FrameAcquisitionStage:
    """Stage: select FrameSource, acquire frames, load into RAM, validate availability."""

    def run(self, context: RunContext, data: PreparedInput) -> AcquiredFrames:
        """
        Get frames via FrameSource; apply max-load cap; load images; return aligned bundle.

        Only successfully loaded frames are returned. frames_nd, frame_paths, frame_refs,
        and metadata["frame_indices"] are positionally aligned (same length, index i refers to same frame).

        Raises:
            ValueError, FileNotFoundError, RuntimeError: From get_frame_source/get_frames or when no frames load.
        """
        settings = context.settings
        job_id = context.job_id
        run_dir = context.run_dir
        logger = context.logger

        frame_source = get_frame_source(data.job_input.input_type)
        bundle = frame_source.get_frames(job_id, run_dir, data.job_input)

        max_load = getattr(settings, "hybrid_max_frames", None)
        if max_load is None or not isinstance(max_load, (int, float)) or max_load <= 0:
            max_load = HYBRID_MAX_FRAMES_LOAD_CAP
        frames_to_load = bundle.frames[: int(max_load)]
        refs = bundle.frame_refs or []
        bundle_indices: Optional[List[int]] = None
        if isinstance(bundle.metadata.get("frame_indices"), list):
            bundle_indices = bundle.metadata["frame_indices"]

        loaded_frames_nd: List[np.ndarray] = []
        loaded_frame_paths: List[Path] = []
        loaded_frame_refs: List[str] = []
        loaded_frame_indices: List[int] = []

        for i, p in enumerate(frames_to_load):
            img = cv2.imread(str(p))
            if img is not None:
                loaded_frames_nd.append(img)
                loaded_frame_paths.append(p)
                loaded_frame_refs.append(refs[i] if i < len(refs) else f"frame_{i}")
                if bundle_indices is not None and i < len(bundle_indices):
                    loaded_frame_indices.append(bundle_indices[i])
                else:
                    loaded_frame_indices.append(i)

        if not loaded_frames_nd:
            logger.warning(
                "No frames could be loaded from bundle (frame_count=%s)",
                bundle.metadata.get("frame_count"),
            )
            raise ValueError("No frames could be loaded from bundle")

        metadata = {**bundle.metadata, "frame_count": len(loaded_frames_nd)}
        metadata["frame_indices"] = loaded_frame_indices

        logger.info("Frames loaded: %d (source=%s)", len(loaded_frames_nd), metadata.get("source", "unknown"))

        return AcquiredFrames(
            frames_nd=loaded_frames_nd,
            frame_paths=loaded_frame_paths,
            metadata=metadata,
            frame_refs=loaded_frame_refs,
        )
