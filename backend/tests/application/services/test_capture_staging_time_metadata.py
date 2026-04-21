"""Sprint 3 — Pillow staging time extraction precedence and UTC normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pytest
from PIL import Image

from src.application.services.capture_staging_time_metadata import PillowCaptureStagingTimeMetadataExtractor
from src.domain.capture.entities import CaptureTimeSource


def _minimal_jpeg_no_exif() -> bytes:
    img = Image.new("RGB", (2, 2), color=(200, 100, 50))
    bio = BytesIO()
    img.save(bio, format="JPEG", quality=90)
    return bio.getvalue()


def test_fallback_uses_ingest_clock_when_no_exif_or_mtime() -> None:
    ext = PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=0.9,
        confidence_mtime=0.55,
        confidence_fallback=0.31,
    )
    ingest = datetime(2026, 6, 1, 15, 0, 0, tzinfo=timezone.utc)
    out = ext.extract(
        raw_bytes=_minimal_jpeg_no_exif(),
        media_content_type="image/jpeg",
        ingest_clock=ingest,
        source_mtime_utc=None,
    )
    assert out.time_source == CaptureTimeSource.FALLBACK_CLOCK
    assert out.time_confidence == pytest.approx(0.31)
    assert out.effective_capture_time == ingest


def test_mtime_precedence_over_fallback() -> None:
    ext = PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=0.9,
        confidence_mtime=0.55,
        confidence_fallback=0.31,
    )
    ingest = datetime(2026, 6, 1, 15, 0, 0, tzinfo=timezone.utc)
    mtime = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    out = ext.extract(
        raw_bytes=_minimal_jpeg_no_exif(),
        media_content_type="image/jpeg",
        ingest_clock=ingest,
        source_mtime_utc=mtime,
    )
    assert out.time_source == CaptureTimeSource.FILE_MTIME
    assert out.effective_capture_time == mtime
