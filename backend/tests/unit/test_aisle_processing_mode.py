"""Unit tests for aisle processing_mode (AUTO / CODE_SCAN_ONLY / VISION_ONLY)."""

from __future__ import annotations

import pytest

from src.application.services.aisle_identification_execution import (
    identification_execution_snapshot_dict,
    resolve_execution_strategy_decision,
)
from src.domain.aisle_identification.modes import AisleIdentificationMode
from src.domain.aisle_identification.processing_mode import (
    AisleProcessingMode,
    DEFAULT_AISLE_PROCESSING_MODE,
    VISION_ONLY_DIRECT_ERROR_CODE,
    parse_aisle_processing_mode,
    processing_mode_from_identification_execution,
)


def test_parse_processing_mode_defaults_to_auto():
    assert parse_aisle_processing_mode(None) is AisleProcessingMode.AUTO
    assert parse_aisle_processing_mode("") is AisleProcessingMode.AUTO
    assert parse_aisle_processing_mode("vision_only") is AisleProcessingMode.VISION_ONLY


def test_parse_processing_mode_rejects_unknown():
    with pytest.raises(ValueError, match="Invalid processing_mode"):
        parse_aisle_processing_mode("LEGACY_LLM")


def test_snapshot_includes_processing_mode():
    decision = resolve_execution_strategy_decision(
        effective_mode=AisleIdentificationMode.CODE_SCAN,
        pipeline_enabled=True,
        code_scan_processing_enabled=True,
    )
    snap = identification_execution_snapshot_dict(
        decision,
        configuration_snapshot_version=1,
        processing_mode="VISION_ONLY",
    )
    assert snap["processing_mode"] == "VISION_ONLY"
    assert snap["feature_flag_state"]["processing_mode"] == "VISION_ONLY"


def test_historical_snapshot_without_processing_mode_defaults_auto():
    assert (
        processing_mode_from_identification_execution({"executed_strategy": "CODE_SCAN"})
        is DEFAULT_AISLE_PROCESSING_MODE
    )
    assert VISION_ONLY_DIRECT_ERROR_CODE == "VISION_ONLY_DIRECT"
