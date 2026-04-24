"""Domain enums for capture sessions — Sprint 1."""

from src.domain.capture.entities import (
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
    CaptureTimeSource,
)


def test_capture_session_status_values_are_stable_strings() -> None:
    assert CaptureSessionStatus.DRAFT.value == "draft"
    assert CaptureSessionStatus.CONFIRMED.value == "confirmed"


def test_item_import_and_assignment_enums() -> None:
    assert CaptureSessionItemImportStatus.IMPORTED.value == "imported"
    assert CaptureSessionItemAssignmentStatus.PENDING.value == "pending"


def test_time_source_enum() -> None:
    assert CaptureTimeSource.EXIF.value == "exif"
    assert CaptureTimeSource.FALLBACK_CLOCK.value == "fallback_clock"
