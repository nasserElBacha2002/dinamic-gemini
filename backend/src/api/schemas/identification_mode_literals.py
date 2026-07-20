"""Shared API Literal aliases for aisle identification mode (Phase 1)."""

from __future__ import annotations

from typing import Literal

IdentificationModeLiteral = Literal["CODE_SCAN", "INTERNAL_OCR", "LEGACY_LLM"]

IdentificationModeSourceLiteral = Literal[
    "REQUEST",
    "AISLE",
    "INVENTORY",
    "CLIENT",
    "SYSTEM_DEFAULT",
    "LEGACY_MIGRATION",
]

ExecutionStrategyLiteral = Literal[
    "LEGACY_LLM", "LEGACY_LLM_TEMPORARY", "CODE_SCAN", "INTERNAL_OCR"
]
