"""Unit tests — conflict error mapping preserves specific ``exc.code`` on the wire."""

from __future__ import annotations

from src.api.errors.error_mapping import mapped_http_exception
from src.api.errors.structured_api_http import (
    AISLE_LOCATION_CONFLICT,
    AISLE_LOCATION_LABEL_CONFLICT,
    ORDERED_CAPTURE_CONFLICT,
    StructuredApiHttpError,
)
from src.application.errors import (
    AisleLocationConflictError,
    AisleLocationLabelConflictError,
    OrderedCaptureSessionConflictError,
)


def test_ordered_capture_conflict_preserves_open_session_exists_code() -> None:
    http = mapped_http_exception(
        OrderedCaptureSessionConflictError(
            "open exists",
            code="ORDERED_CAPTURE_OPEN_SESSION_EXISTS",
        )
    )
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == 409
    assert http.error_code == "ORDERED_CAPTURE_OPEN_SESSION_EXISTS"


def test_ordered_capture_conflict_preserves_sequence_conflict_code() -> None:
    http = mapped_http_exception(
        OrderedCaptureSessionConflictError(
            "seq conflict",
            code="ORDERED_CAPTURE_SEQUENCE_CONFLICT",
        )
    )
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == "ORDERED_CAPTURE_SEQUENCE_CONFLICT"


def test_ordered_capture_conflict_unknown_code_falls_back_to_default() -> None:
    http = mapped_http_exception(
        OrderedCaptureSessionConflictError("x", code="NOT_AN_ALLOWED_CODE")
    )
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == ORDERED_CAPTURE_CONFLICT


def test_aisle_location_conflict_preserves_inactive_code() -> None:
    http = mapped_http_exception(
        AisleLocationConflictError("inactive", code="AISLE_LOCATION_INACTIVE")
    )
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == 409
    assert http.error_code == "AISLE_LOCATION_INACTIVE"


def test_aisle_location_conflict_preserves_code_conflict() -> None:
    http = mapped_http_exception(
        AisleLocationConflictError("dup", code="AISLE_LOCATION_CODE_CONFLICT")
    )
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == "AISLE_LOCATION_CODE_CONFLICT"


def test_aisle_location_conflict_unknown_code_falls_back() -> None:
    http = mapped_http_exception(
        AisleLocationConflictError("x", code="WEIRD_CODE")
    )
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == AISLE_LOCATION_CONFLICT


def test_aisle_location_label_conflict_preserves_default_allowed() -> None:
    http = mapped_http_exception(
        AisleLocationLabelConflictError(
            "label conflict",
            code="AISLE_LOCATION_LABEL_CONFLICT",
        )
    )
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == AISLE_LOCATION_LABEL_CONFLICT


def test_aisle_location_label_conflict_unknown_falls_back() -> None:
    http = mapped_http_exception(
        AisleLocationLabelConflictError("x", code="OTHER_LABEL_CODE")
    )
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == AISLE_LOCATION_LABEL_CONFLICT
