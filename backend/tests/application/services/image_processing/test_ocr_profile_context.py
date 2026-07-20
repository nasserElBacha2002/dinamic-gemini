"""OCR profile context resolver — invalid ≠ absent."""

from __future__ import annotations

from src.application.services.image_processing.ocr_profile_context import (
    OcrProfileResolveStatus,
    resolve_ocr_profile_context,
)


def test_absent_snapshot_allowed() -> None:
    ctx = resolve_ocr_profile_context(None)
    assert ctx.status is OcrProfileResolveStatus.ABSENT
    assert not ctx.is_invalid


def test_invalid_snapshot_fail_closed() -> None:
    ctx = resolve_ocr_profile_context(
        {
            "configuration": {
                "internal_code_sources": [
                    {"field_key": "EAN", "priority": 1, "enabled": True}
                ],
                "validation_rules": {"code": {"regex": "a+"}},
            }
        }
    )
    assert ctx.status is OcrProfileResolveStatus.INVALID
    assert ctx.error_code == "PROFILE_SNAPSHOT_INVALID"
    assert ctx.is_invalid


def test_valid_snapshot_parsed_once_instance() -> None:
    snapshot = {
        "configuration": {
            "schema_version": 1,
        }
    }
    ctx = resolve_ocr_profile_context(snapshot)
    assert ctx.status is OcrProfileResolveStatus.VALID
    assert ctx.configuration is not None
