"""Shared contracts for per-image processing strategies (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)


class ExecutionScope(str, Enum):
    """Physical execution unit vs logical per-asset bookkeeping."""

    AISLE_BATCH = "AISLE_BATCH"
    SINGLE_ASSET = "SINGLE_ASSET"


class ImageResultStatus(str, Enum):
    RESOLVED_INTERNAL = "RESOLVED_INTERNAL"
    RESOLVED_EXTERNAL = "RESOLVED_EXTERNAL"
    UNRECOGNIZED = "UNRECOGNIZED"
    FAILED_TECHNICAL = "FAILED_TECHNICAL"
    PENDING_MANUAL_REVIEW = "PENDING_MANUAL_REVIEW"


@dataclass(frozen=True)
class ImageProcessingContext:
    job_id: str
    asset_id: str
    aisle_id: str
    inventory_id: str
    client_id: str | None
    identification_mode: AisleIdentificationMode
    execution_strategy: AisleIdentificationExecutionStrategy
    configuration_snapshot_version: int
    provider_name: str | None
    model_name: str | None
    prompt_key: str | None
    prompt_version: str | None
    attempt_number: int
    execution_scope: ExecutionScope = ExecutionScope.SINGLE_ASSET
    asset_reference: str | None = None


@dataclass
class ImageProcessingResult:
    job_id: str
    asset_id: str
    status: ImageResultStatus
    processing_mode: str
    resolved_by: str | None = None
    internal_code: str | None = None
    quantity: float | None = None
    additional_fields: dict[str, Any] = field(default_factory=dict)
    raw_result: dict[str, Any] | None = None
    normalized_result: dict[str, Any] | None = None
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] | None = None
    provider_name: str | None = None
    model_name: str | None = None
    processing_duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    execution_scope: ExecutionScope = ExecutionScope.SINGLE_ASSET
    logical_asset_attempt: bool = True


class ProcessingStrategy(Protocol):
    """Provider-agnostic strategy for processing one logical asset context.

    Phase 2 ``LegacyLlmProcessingStrategy`` may execute as AISLE_BATCH and still
    emit logical per-asset results after the batch completes.
    """

    @property
    def strategy_key(self) -> str: ...

    def process(self, context: ImageProcessingContext) -> ImageProcessingResult: ...
