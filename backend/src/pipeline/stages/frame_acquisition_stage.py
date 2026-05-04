"""
FrameAcquisitionStage — obtain frames from FrameSource and load into memory (v2.3.C).

Uses current get_frame_source + get_frames logic; applies same max-load cap and validation.
Returns only successfully loaded frames; all output collections are positionally aligned.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from src.frames.sources.factory import get_frame_source
from src.pipeline.context.run_context import RunContext
from src.pipeline.stages.input_preparation_stage import PreparedInput

# Hard cap when settings.hybrid_max_frames is unset (single source of truth for load cap)
HYBRID_MAX_FRAMES_LOAD_CAP = 48


@dataclass
class AcquiredFrames:
    """Output of FrameAcquisitionStage: frames in memory and metadata for analysis. All lists are positionally aligned."""

    frames_nd: list[np.ndarray]
    frame_paths: list[Path]
    metadata: dict
    frame_refs: list[str]


class FrameAcquisitionStage:
    """Stage: select FrameSource, acquire frames, load into RAM, validate availability."""

    def _read_image(self, path: Path):  # type: ignore[no-untyped-def]
        """Isolated native image-read boundary for future timeout/process guarding."""
        return cv2.imread(str(path))

    def _emit_substep(
        self,
        context: RunContext,
        *,
        substep: str,
        event: str,
        details: dict | None = None,
        duration_ms: int | None = None,
        level: str = "info",
    ) -> None:
        context.emit_stage_event(
            stage="FrameAcquisitionStage",
            substep=substep,
            event=event,
            details=details,
            duration_ms=duration_ms,
            level=level,
        )

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

        manifest_started = time.monotonic()
        self._emit_substep(
            context,
            substep="manifest_load",
            event="substep.started",
            details={
                "input_type": data.job_input.input_type,
                "manifest_path": data.job_input.input_manifest_path,
                "photos_dir": data.job_input.photos_dir,
            },
        )
        frame_source = get_frame_source(data.job_input.input_type)
        self._emit_substep(
            context,
            substep="manifest_load",
            event="substep.completed",
            duration_ms=int((time.monotonic() - manifest_started) * 1000),
            details={"frame_source": type(frame_source).__name__},
        )

        scan_started = time.monotonic()
        self._emit_substep(context, substep="photos_dir_scan", event="substep.started")
        bundle = frame_source.get_frames(job_id, run_dir, data.job_input)
        self._emit_substep(
            context,
            substep="photos_dir_scan",
            event="substep.completed",
            duration_ms=int((time.monotonic() - scan_started) * 1000),
            details={
                "bundle_frame_count": len(bundle.frames),
                "source": bundle.metadata.get("source"),
            },
        )

        max_load = getattr(settings, "hybrid_max_frames", None)
        if max_load is None or not isinstance(max_load, (int, float)) or max_load <= 0:
            max_load = HYBRID_MAX_FRAMES_LOAD_CAP
        frames_to_load = bundle.frames[: int(max_load)]
        refs = bundle.frame_refs or []
        bundle_indices: list[int] | None = None
        if isinstance(bundle.metadata.get("frame_indices"), list):
            bundle_indices = bundle.metadata["frame_indices"]

        self._emit_substep(
            context,
            substep="file_enumeration",
            event="substep.completed",
            details={
                "available_frames": len(bundle.frames),
                "frames_to_load": len(frames_to_load),
                "max_load": int(max_load),
            },
        )

        loaded_frames_nd: list[np.ndarray] = []
        loaded_frame_paths: list[Path] = []
        loaded_frame_refs: list[str] = []
        loaded_frame_indices: list[int] = []

        for i, p in enumerate(frames_to_load):
            context.check_cancellation(
                stage="FrameAcquisitionStage",
                substep="file_validation",
                reason="Job cancellation requested during frame acquisition",
            )
            file_details = {
                "index": i,
                "path": str(p),
                "ref": refs[i] if i < len(refs) else f"frame_{i}",
                "exists": p.exists(),
                "file_size_bytes": (p.stat().st_size if p.exists() else None),
            }
            self._emit_substep(
                context,
                substep="file_validation",
                event="substep.started",
                details=file_details,
            )
            if not p.exists() or not p.is_file():
                self._emit_substep(
                    context,
                    substep="file_validation",
                    event="substep.failed",
                    details=file_details,
                    level="error",
                )
                continue
            self._emit_substep(
                context,
                substep="file_validation",
                event="substep.completed",
                details=file_details,
            )

            open_started = time.monotonic()
            self._emit_substep(
                context,
                substep="image_open",
                event="substep.started",
                details=file_details,
            )
            context.metadata["frame_acquisition_last_path"] = str(p)
            img = self._read_image(p)
            context.check_cancellation(
                stage="FrameAcquisitionStage",
                substep="image_open",
                reason="Job cancellation requested after image read",
            )
            self._emit_substep(
                context,
                substep="image_open",
                event="substep.completed",
                details=file_details,
                duration_ms=int((time.monotonic() - open_started) * 1000),
            )
            decode_details = {
                **file_details,
                "decoded": img is not None,
                "shape": list(img.shape) if img is not None else None,
            }
            self._emit_substep(
                context,
                substep="image_decode",
                event="substep.completed" if img is not None else "substep.failed",
                details=decode_details,
                level="info" if img is not None else "error",
            )
            if img is not None:
                self._emit_substep(
                    context,
                    substep="image_normalization",
                    event="substep.completed",
                    details=decode_details,
                )
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
            self._emit_substep(
                context,
                substep="frame_collection_completed",
                event="substep.failed",
                details={"bundle_frame_count": bundle.metadata.get("frame_count")},
                level="error",
            )
            raise ValueError("No frames could be loaded from bundle")

        metadata = {**bundle.metadata, "frame_count": len(loaded_frames_nd)}
        metadata["frame_indices"] = loaded_frame_indices

        self._emit_substep(
            context,
            substep="frame_collection_completed",
            event="substep.completed",
            details={
                "loaded_frames": len(loaded_frames_nd),
                "source": metadata.get("source", "unknown"),
            },
        )
        logger.info(
            "Frames loaded: %d (source=%s)",
            len(loaded_frames_nd),
            metadata.get("source", "unknown"),
        )

        return AcquiredFrames(
            frames_nd=loaded_frames_nd,
            frame_paths=loaded_frame_paths,
            metadata=metadata,
            frame_refs=loaded_frame_refs,
        )
