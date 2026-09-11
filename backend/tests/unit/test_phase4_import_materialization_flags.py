"""Flag composition for Phase 4 import materialization."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.env_settings.grouped_settings import LimitsAndSchemaSettings


def test_import_materialization_requires_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSITION_FLEXIBLE_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_PREEXISTENCE_REQUIRED", "false")
    monkeypatch.setenv("POSITION_AUTO_MATERIALIZATION_ENABLED", "false")
    monkeypatch.setenv("POSITION_IMPORT_MATERIALIZATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_FLEXIBLE_CODE_SCAN_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_VISION_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_MOBILE_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_IMPORT_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_REVIEW_ENABLED", "false")
    with pytest.raises(ValidationError):
        LimitsAndSchemaSettings()


def test_import_materialization_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSITION_IMPORT_MATERIALIZATION_ENABLED", raising=False)
    monkeypatch.setenv("POSITION_FLEXIBLE_VALIDATION_ENABLED", "false")
    monkeypatch.setenv("POSITION_PREEXISTENCE_REQUIRED", "true")
    monkeypatch.setenv("POSITION_AUTO_MATERIALIZATION_ENABLED", "false")
    monkeypatch.setenv("POSITION_SIGNATURE_POLICY", "REQUIRED")
    monkeypatch.setenv("POSITION_FLEXIBLE_CODE_SCAN_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_VISION_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_MOBILE_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_IMPORT_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_REVIEW_ENABLED", "false")
    settings = LimitsAndSchemaSettings()
    assert settings.position_import_materialization_enabled is False
    assert settings.position_flexible_code_scan_enabled is False
    assert settings.position_signature_policy == "REQUIRED"
