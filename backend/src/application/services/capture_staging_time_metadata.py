"""Pillow-based staging time extraction — Sprint 3 (EXIF → optional mtime → ingest clock).

EXIF datetime policy (MVP)
--------------------------
Standard EXIF date/time strings carry **no timezone**. We do **not** infer camera offset or
location. For deterministic ordering and persistence, parsed EXIF wall-clock values are
stored as **timezone-aware UTC** using the same numeric fields (:func:`datetime.replace` with
``tzinfo=timezone.utc``). That is **not** a claim that the camera was in UTC; it is an explicit
Sprint 3 limitation documented for auditability. Prefer ``FALLBACK_CLOCK`` / client ``mtime``
when wall-clock accuracy matters more than embedded EXIF strings.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from src.application.ports.capture_staging_time import (
    CaptureStagingTimeMetadataExtractor,
    ExtractedCaptureStagingTime,
)
from src.domain.capture.entities import CaptureTimeSource

logger = logging.getLogger(__name__)

# EXIF tags: DateTimeOriginal, DateTimeDigitized, DateTime (fallback)
_EXIF_DATETIME_TAGS = (36867, 36868, 306)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


def _parse_exif_datetime_string(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    # "2023:12:01 14:30:00" per EXIF spec; optional subsecond fragments ignored for determinism.
    m = re.match(r"^(\d{4}):(\d{2}):(\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})", s)
    if not m:
        return None
    y, mo, d, h, mi, se = (int(x) for x in m.groups())
    try:
        # Naive EXIF wall clock → UTC-aware **same numbers** (MVP; see module docstring).
        return datetime(y, mo, d, h, mi, se, tzinfo=timezone.utc)
    except ValueError:
        return None


def _try_exif_datetime(raw_bytes: bytes) -> datetime | None:
    try:
        img = Image.open(BytesIO(raw_bytes))
        try:
            exif = img.getexif()
        except Exception:  # noqa: BLE001
            return None
        if exif is None:
            return None
        for tag in _EXIF_DATETIME_TAGS:
            val = exif.get(tag)
            if val is None:
                continue
            parsed = _parse_exif_datetime_string(str(val))
            if parsed is not None:
                return parsed
    except (UnidentifiedImageError, OSError, ValueError) as e:
        logger.debug("capture time EXIF: skip (%s)", e)
    except Exception:  # noqa: BLE001
        logger.warning("capture time EXIF: unexpected error", exc_info=True)
    return None


class PillowCaptureStagingTimeMetadataExtractor(CaptureStagingTimeMetadataExtractor):
    """Deterministic precedence: parseable EXIF → optional ``source_mtime_utc`` → ``ingest_clock``.

    ``media_content_type`` is accepted for port compatibility; this implementation probes
    ``raw_bytes`` with Pillow regardless of MIME (call sites already validate capture media).
    """

    def __init__(
        self, *, confidence_exif: float, confidence_mtime: float, confidence_fallback: float
    ) -> None:
        self._c_exif = float(confidence_exif)
        self._c_mtime = float(confidence_mtime)
        self._c_fb = float(confidence_fallback)

    def extract(
        self,
        *,
        raw_bytes: bytes,
        media_content_type: str,
        ingest_clock: datetime,
        source_mtime_utc: datetime | None = None,
    ) -> ExtractedCaptureStagingTime:
        _ = media_content_type  # Port / future MIME-aware paths; Sprint 3 Pillow probes bytes only.
        ingest = _ensure_utc(ingest_clock)
        exif_dt = _try_exif_datetime(raw_bytes)
        if exif_dt is not None:
            return ExtractedCaptureStagingTime(
                effective_capture_time=_ensure_utc(exif_dt),
                time_source=CaptureTimeSource.EXIF,
                time_confidence=self._c_exif,
            )
        if source_mtime_utc is not None:
            return ExtractedCaptureStagingTime(
                effective_capture_time=_ensure_utc(source_mtime_utc),
                time_source=CaptureTimeSource.FILE_MTIME,
                time_confidence=self._c_mtime,
            )
        return ExtractedCaptureStagingTime(
            effective_capture_time=ingest,
            time_source=CaptureTimeSource.FALLBACK_CLOCK,
            time_confidence=self._c_fb,
        )
