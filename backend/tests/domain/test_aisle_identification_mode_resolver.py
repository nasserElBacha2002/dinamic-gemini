"""Unit tests for aisle identification mode resolver (Phase 1)."""

from __future__ import annotations

import pytest

from src.domain.aisle_identification.modes import (
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.aisle_identification.resolver import resolve_aisle_identification_mode


def test_request_override_has_priority() -> None:
    r = resolve_aisle_identification_mode(
        request_mode=AisleIdentificationMode.CODE_SCAN,
        aisle_mode=AisleIdentificationMode.INTERNAL_OCR,
        inventory_mode=AisleIdentificationMode.LEGACY_LLM,
        client_mode=AisleIdentificationMode.LEGACY_LLM,
    )
    assert r.effective_mode == AisleIdentificationMode.CODE_SCAN
    assert r.source == AisleIdentificationModeSource.REQUEST


def test_aisle_beats_inventory_and_client() -> None:
    r = resolve_aisle_identification_mode(
        aisle_mode=AisleIdentificationMode.INTERNAL_OCR,
        inventory_mode=AisleIdentificationMode.CODE_SCAN,
        client_mode=AisleIdentificationMode.LEGACY_LLM,
    )
    assert r.effective_mode == AisleIdentificationMode.INTERNAL_OCR
    assert r.source == AisleIdentificationModeSource.AISLE


def test_inventory_beats_client() -> None:
    r = resolve_aisle_identification_mode(
        inventory_mode=AisleIdentificationMode.CODE_SCAN,
        client_mode=AisleIdentificationMode.INTERNAL_OCR,
    )
    assert r.effective_mode == AisleIdentificationMode.CODE_SCAN
    assert r.source == AisleIdentificationModeSource.INVENTORY


def test_client_when_no_overrides() -> None:
    r = resolve_aisle_identification_mode(client_mode=AisleIdentificationMode.CODE_SCAN)
    assert r.effective_mode == AisleIdentificationMode.CODE_SCAN
    assert r.source == AisleIdentificationModeSource.CLIENT


def test_system_default_legacy_llm() -> None:
    r = resolve_aisle_identification_mode()
    assert r.effective_mode == AisleIdentificationMode.LEGACY_LLM
    assert r.source == AisleIdentificationModeSource.SYSTEM_DEFAULT


def test_invalid_values_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid identification_mode"):
        resolve_aisle_identification_mode(request_mode="AUTO")


def test_null_override_inherits() -> None:
    r = resolve_aisle_identification_mode(
        aisle_mode=None,
        inventory_mode=AisleIdentificationMode.INTERNAL_OCR,
        client_mode=AisleIdentificationMode.CODE_SCAN,
    )
    assert r.effective_mode == AisleIdentificationMode.INTERNAL_OCR
    assert r.source == AisleIdentificationModeSource.INVENTORY


def test_blank_string_treated_as_inherit() -> None:
    r = resolve_aisle_identification_mode(
        aisle_mode="  ",
        inventory_mode=None,
        client_mode=AisleIdentificationMode.CODE_SCAN,
    )
    assert r.effective_mode == AisleIdentificationMode.CODE_SCAN
    assert r.source == AisleIdentificationModeSource.CLIENT
