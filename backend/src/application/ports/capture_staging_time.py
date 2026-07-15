"""Port for deriving capture staging time metadata (Sprint 3) — EXIF / mtime / clock precedence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO

from src.domain.capture.entities import CaptureTimeSource


@dataclass(frozen=True)
class ExtractedCaptureStagingTime:
    """UTC-normalized capture instant and provenance for a staging blob."""

    effective_capture_time: datetime
    time_source: CaptureTimeSource
    time_confidence: float


class CaptureStagingTimeMetadataExtractor(ABC):
    """Derives ``effective_capture_time`` / ``time_source`` / ``time_confidence`` for staging bytes."""

    @abstractmethod
    def extract(
        self,
        *,
        raw_bytes: bytes | None = None,
        file_obj: BinaryIO | None = None,
        media_content_type: str,
        ingest_clock: datetime,
        source_mtime_utc: datetime | None = None,
    ) -> ExtractedCaptureStagingTime:
        """``ingest_clock`` must be timezone-aware UTC. ``source_mtime_utc`` optional client/storage mtime.

        Exactly one of ``raw_bytes`` / ``file_obj`` must be provided. ``file_obj`` is preferred
        for large uploads (avoids a full in-memory copy); implementations must restore the
        original stream position (``seek(0)``) before returning so callers can pass the same
        object straight to storage. ``raw_bytes`` remains supported for call sites that already
        hold the bytes in memory (e.g. tests, small payloads).

        ``media_content_type`` is part of the port for **wire stability** and future MIME-aware
        extraction (e.g. skip non-image branches without changing call sites). Implementations
        may ignore it when they probe the image bytes directly (Sprint 3 Pillow path).
        """
