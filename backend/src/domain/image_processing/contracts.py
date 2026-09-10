"""Shared contracts for per-image processing strategies (Phase 2)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
)
from src.domain.product_labels.processed import ProcessedProductLabel

RAW_EVIDENCE_HASH_ALGORITHM = "sha256-utf8-v1"
VISION_POSITION_DETECTOR_NAME = "vision_candidate_bridge"
VISION_POSITION_DETECTOR_VERSION = "vision-position-canonical-1.0.0"


@dataclass(frozen=True)
class RawEvidenceMetadata:
    """Non-reversible metadata for the exact, pre-normalization input."""

    payload_hash: str
    utf8_length: int
    hash_algorithm: str = RAW_EVIDENCE_HASH_ALGORITHM


@dataclass(frozen=True)
class VisionPositionEvidence:
    """Authoritative validated Vision position input for persistence."""

    recognition: CanonicalPositionRecognition
    client_id: str
    detector_name: str
    detector_version: str
    raw_evidence: RawEvidenceMetadata

    def __post_init__(self) -> None:
        if self.recognition.source is not PositionRecognitionSource.VISION:
            raise ValueError("Vision evidence recognition source must be VISION")
        if self.recognition.raw_code is None:
            raise ValueError("Vision evidence requires the original raw code")
        if not self.client_id.strip():
            raise ValueError("Vision evidence client_id must not be blank")
        if not self.detector_name.strip() or not self.detector_version.strip():
            raise ValueError("Vision evidence detector identity must not be blank")
        if not self.raw_evidence.payload_hash.strip() or self.raw_evidence.utf8_length < 0:
            raise ValueError("Vision raw evidence metadata is invalid")
        raw_bytes = self.recognition.raw_code.encode("utf-8")
        if self.raw_evidence.utf8_length != len(raw_bytes):
            raise ValueError("Vision raw evidence length does not match raw code")
        if self.raw_evidence.hash_algorithm != RAW_EVIDENCE_HASH_ALGORITHM:
            raise ValueError("Unsupported Vision raw evidence hash algorithm")
        if self.raw_evidence.payload_hash != hashlib.sha256(raw_bytes).hexdigest():
            raise ValueError("Vision raw evidence hash does not match raw code")


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
    # Phase 6 — immutable profile snapshot + feature flags from job engine_params.
    supplier_extraction_profile: dict[str, Any] | None = None
    profile_aware_validation_enabled: bool = False
    reference_template_annotations_enabled: bool = False
    # Phase 2 — label profile snapshot + prebuilt validation context (job-scoped).
    label_profiles: dict[str, Any] | None = None
    label_validation_context: LabelValidationContext | None = None


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
    #: CODE_SCAN multi-product: 0..N typed physical product labels (D1 after registry resolve).
    product_results: list[ProcessedProductLabel] = field(default_factory=list)
    #: Authoritative Vision position evidence; legacy ``evidence`` is projection-only.
    vision_position_evidence: tuple[VisionPositionEvidence, ...] = ()


class ProcessingStrategy(Protocol):
    """Provider-agnostic strategy for processing one logical asset context.

    Phase 2 ``LegacyLlmProcessingStrategy`` may execute as AISLE_BATCH and still
    emit logical per-asset results after the batch completes.
    """

    @property
    def strategy_key(self) -> str: ...

    def process(
        self, context: ImageProcessingContext, asset: Any = None
    ) -> ImageProcessingResult: ...
