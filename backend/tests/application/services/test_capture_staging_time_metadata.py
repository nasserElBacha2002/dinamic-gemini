"""Sprint 3 — Pillow staging time extraction precedence and UTC normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pytest
from PIL import Image

from src.application.services import capture_staging_time_metadata as staging_time_mod
from src.application.services.capture_staging_time_metadata import (
    PillowCaptureStagingTimeMetadataExtractor,
)
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


def test_exif_naive_datetime_string_becomes_utc_aware_same_wall_clock_mvp() -> None:
    """EXIF strings have no TZ; policy is deterministic UTC tagging (see module docstring), not camera TZ."""
    doc = staging_time_mod.__doc__ or ""
    assert "no timezone" in doc.lower()
    assert "UTC" in doc
    ext = PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=0.9,
        confidence_mtime=0.55,
        confidence_fallback=0.31,
    )
    img = Image.new("RGB", (2, 2))
    exif = img.getexif()
    exif[0x9003] = "2019:07:20 14:05:03"  # DateTimeOriginal; naive wall clock per EXIF spec
    bio = BytesIO()
    img.save(bio, format="JPEG", exif=exif, quality=90)
    ingest = datetime(2026, 6, 1, 15, 0, 0, tzinfo=timezone.utc)
    out = ext.extract(
        raw_bytes=bio.getvalue(),
        media_content_type="image/jpeg",
        ingest_clock=ingest,
        source_mtime_utc=None,
    )
    assert out.time_source == CaptureTimeSource.EXIF
    assert out.effective_capture_time == datetime(2019, 7, 20, 14, 5, 3, tzinfo=timezone.utc)


def test_exif_branch_does_not_depend_on_media_content_type() -> None:
    """MIME is on the port for stability; Pillow path still reads EXIF from bytes."""
    ext = PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=0.9,
        confidence_mtime=0.55,
        confidence_fallback=0.31,
    )
    img = Image.new("RGB", (2, 2))
    exif = img.getexif()
    exif[0x9003] = "2020:01:02 03:04:05"
    bio = BytesIO()
    img.save(bio, format="JPEG", exif=exif, quality=90)
    ingest = datetime(2026, 6, 1, 15, 0, 0, tzinfo=timezone.utc)
    out = ext.extract(
        raw_bytes=bio.getvalue(),
        media_content_type="application/octet-stream",
        ingest_clock=ingest,
        source_mtime_utc=None,
    )
    assert out.time_source == CaptureTimeSource.EXIF


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


def test_exif_from_file_obj_keeps_stream_open_and_rewinds_to_zero() -> None:
    """Caller's stream must remain open and positioned at 0 after EXIF probe."""
    img = Image.new("RGB", (2, 2))
    exif = img.getexif()
    exif[0x9003] = "2018:03:04 05:06:07"
    bio = BytesIO()
    img.save(bio, format="JPEG", exif=exif, quality=90)
    stream = BytesIO(bio.getvalue())
    stream.seek(12)  # not at start before extract
    assert not stream.closed

    ext = PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=0.9, confidence_mtime=0.55, confidence_fallback=0.31
    )
    out = ext.extract(
        file_obj=stream,
        media_content_type="image/jpeg",
        ingest_clock=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert out.time_source == CaptureTimeSource.EXIF
    assert not stream.closed
    assert stream.tell() == 0


def test_invalid_file_obj_still_rewinds_and_stays_open() -> None:
    stream = BytesIO(b"not-an-image")
    stream.seek(3)
    ext = PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=0.9, confidence_mtime=0.55, confidence_fallback=0.31
    )
    out = ext.extract(
        file_obj=stream,
        media_content_type="image/jpeg",
        ingest_clock=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert out.time_source == CaptureTimeSource.FALLBACK_CLOCK
    assert not stream.closed
    assert stream.tell() == 0


def test_pillow_internal_error_still_rewinds_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = BytesIO(_minimal_jpeg_no_exif())
    stream.seek(5)

    def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("synthetic pillow failure")

    monkeypatch.setattr(staging_time_mod.Image, "open", _boom)
    ext = PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=0.9, confidence_mtime=0.55, confidence_fallback=0.31
    )
    out = ext.extract(
        file_obj=stream,
        media_content_type="image/jpeg",
        ingest_clock=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert out.time_source == CaptureTimeSource.FALLBACK_CLOCK
    assert not stream.closed
    assert stream.tell() == 0
