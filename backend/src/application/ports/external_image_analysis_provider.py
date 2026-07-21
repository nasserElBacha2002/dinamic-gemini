"""Phase 5 — port for single-image external label analysis (provider-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class ExternalAnalysisStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    AMBIGUOUS = "AMBIGUOUS"
    NO_RESULT = "NO_RESULT"
    FAILED_TECHNICAL = "FAILED_TECHNICAL"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class ExternalImageInput:
    content: bytes
    mime_type: str = "image/jpeg"
    asset_id: str = ""
    original_filename: str | None = None


@dataclass(frozen=True)
class ExternalAnalysisContext:
    job_id: str
    asset_id: str
    client_id: str | None
    prompt_key: str
    prompt_version: str | None
    timeout_seconds: float
    max_image_dimension: int
    quantity_max: int
    configuration_snapshot_version: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExternalAnalysisResult:
    status: ExternalAnalysisStatus
    internal_code: str | None = None
    quantity: int | None = None
    additional_fields: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    provider_name: str = ""
    model_name: str = ""
    prompt_version: str | None = None
    schema_version: str | None = None
    duration_ms: int | None = None
    usage: dict[str, Any] | None = None
    estimated_cost: float | None = None
    raw_reference: str | None = None
    normalized_result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


class ExternalImageAnalysisProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def analyze_image(
        self,
        image: ExternalImageInput,
        context: ExternalAnalysisContext,
    ) -> ExternalAnalysisResult: ...


__all__ = [
    "ExternalAnalysisContext",
    "ExternalAnalysisResult",
    "ExternalAnalysisStatus",
    "ExternalImageAnalysisProvider",
    "ExternalImageInput",
]
