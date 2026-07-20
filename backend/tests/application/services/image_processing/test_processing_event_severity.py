"""Severity normalization for processing_events CHECK constraint."""

from __future__ import annotations

from src.application.services.image_processing.processing_event_publisher import (
    normalize_processing_event_severity,
)
from src.pipeline.secret_redaction import redact_secrets_in_value


def test_normalize_warning_to_warn() -> None:
    assert normalize_processing_event_severity("WARNING") == "WARN"
    assert normalize_processing_event_severity("warning") == "WARN"
    assert normalize_processing_event_severity("WARN") == "WARN"
    assert normalize_processing_event_severity("INFO") == "INFO"
    assert normalize_processing_event_severity("ERROR") == "ERROR"
    assert normalize_processing_event_severity("CRITICAL") == "ERROR"
    assert normalize_processing_event_severity("weird") == "INFO"


def test_ocr_token_count_keys_not_redacted_as_secrets() -> None:
    out = redact_secrets_in_value(
        {
            "normalized_token_count": 65,
            "numeric_token_count": 12,
            "access_token": "secret-value",
        }
    )
    assert out["normalized_token_count"] == 65
    assert out["numeric_token_count"] == 12
    assert out["access_token"] == "[REDACTED]"
