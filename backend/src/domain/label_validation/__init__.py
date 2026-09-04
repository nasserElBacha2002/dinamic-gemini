"""Phase 2 — unified label validation contracts (recognition ≠ validation).

Distinct from ``domain.labels.NormalizedLabel`` (inventory merge layer).
These types are the CODE_SCAN / future Vision/TXT validation boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation.context import LabelValidationContext as LabelValidationContext


class LabelValidationStatus(str, Enum):
    """Outcome of deterministic validation (not recognition)."""

    VALID = "VALID"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    AMBIGUOUS = "AMBIGUOUS"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"


class LabelValidationErrorCode(str, Enum):
    """Stable validation error codes (reuse existing product-label codes where mapped)."""

    LABEL_PATTERN_MISMATCH = "LABEL_PATTERN_MISMATCH"
    LABEL_REQUIRED_FIELD_MISSING = "LABEL_REQUIRED_FIELD_MISSING"
    LABEL_FIELD_INVALID = "LABEL_FIELD_INVALID"
    LABEL_KIND_MISMATCH = "LABEL_KIND_MISMATCH"
    LABEL_SYMBOLOGY_REJECTED = "LABEL_SYMBOLOGY_REJECTED"
    LABEL_PROFILE_CONFIGURATION_INVALID = "LABEL_PROFILE_CONFIGURATION_INVALID"
    SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED = "SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED"
    DINAMIC_FORMAT_INVALID = "DINAMIC_FORMAT_INVALID"
    DINAMIC_CHECKSUM_FAILED = "DINAMIC_CHECKSUM_FAILED"
    DINAMIC_POSITION_INVALID = "DINAMIC_POSITION_INVALID"
    AMBIGUOUS_LABEL_KIND = "AMBIGUOUS_LABEL_KIND"
    LABEL_PROFILE_SOURCE_MISMATCH = "LABEL_PROFILE_SOURCE_MISMATCH"
    LABEL_PREFIX_MISMATCH = "LABEL_PREFIX_MISMATCH"
    LABEL_SUFFIX_MISMATCH = "LABEL_SUFFIX_MISMATCH"
    LABEL_LENGTH_MISMATCH = "LABEL_LENGTH_MISMATCH"
    LABEL_CHARSET_MISMATCH = "LABEL_CHARSET_MISMATCH"
    LABEL_SEGMENT_COUNT_MISMATCH = "LABEL_SEGMENT_COUNT_MISMATCH"
    LABEL_FIELD_MAPPING_INVALID = "LABEL_FIELD_MAPPING_INVALID"
    LABEL_CHECKSUM_FAILED = "LABEL_CHECKSUM_FAILED"
    LABEL_GS1_INVALID = "LABEL_GS1_INVALID"
    LABEL_GS1_REQUIRED_AI_MISSING = "LABEL_GS1_REQUIRED_AI_MISSING"
    LABEL_GS1_CHECK_DIGIT_FAILED = "LABEL_GS1_CHECK_DIGIT_FAILED"
    LABEL_GS1_FIELD_INVALID = "LABEL_GS1_FIELD_INVALID"
    LABEL_GS1_SEPARATOR_INVALID = "LABEL_GS1_SEPARATOR_INVALID"
    LABEL_PROFILE_EXAMPLE_MISMATCH = "LABEL_PROFILE_EXAMPLE_MISMATCH"
    NOT_OUR_FORMAT = "NOT_OUR_FORMAT"


class RecognitionSource(str, Enum):
    CODE_SCAN = "CODE_SCAN"
    TXT = "TXT"
    CSV = "CSV"
    OCR = "OCR"
    VISION = "VISION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CandidateLabel:
    """Unrecognized/unvalidated payload from a recognition mechanism.

    Does not claim validity. ``label_kind`` may be a hint from the recognizer;
    the validator may still reject or reclassify within policy.
    """

    raw_payload: str
    recognition_source: RecognitionSource = RecognitionSource.CODE_SCAN
    label_kind_hint: LabelKind | None = None
    symbology: str | None = None
    label_id: str | None = None
    sku: str | None = None
    quantity: int | float | None = None
    position_id: str | None = None
    pallet: str | None = None
    side: str | None = None
    level: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.raw_payload is None:
            raise ValueError("CandidateLabel.raw_payload is required")
        # Allow empty raw only when structured fields are present (future TXT).
        if not str(self.raw_payload).strip() and not any(
            (
                self.label_id,
                self.sku,
                self.position_id,
                self.pallet,
            )
        ):
            raise ValueError("CandidateLabel requires raw_payload or identity fields")


@dataclass(frozen=True)
class NormalizedItemLabel:
    """Validated ITEM label — strong invariants (not all-nullable).

    Logistic units (SSCC/LPN) may set ``label_id`` without inventing a SKU.
    At least one of ``sku`` or ``label_id`` must be present.
    """

    label_id: str | None
    sku: str | None
    quantity: int | None
    raw_payload: str
    profile_source: LabelProfileSource
    format_version: str | None = None
    symbology: str | None = None
    checksum_ok: bool | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    kind: LabelKind = field(default=LabelKind.ITEM, init=False)

    def __post_init__(self) -> None:
        has_sku = bool((self.sku or "").strip())
        has_label = bool((self.label_id or "").strip())
        if not has_sku and not has_label:
            raise ValueError("NormalizedItemLabel requires sku or label_id")
        if not (self.raw_payload or "").strip():
            raise ValueError("NormalizedItemLabel.raw_payload is required")


@dataclass(frozen=True)
class NormalizedPositionLabel:
    """Validated POSITION label — strong invariants."""

    position_id: str
    pallet: str | None
    side: str | None
    raw_payload: str
    profile_source: LabelProfileSource
    level: str | None = None
    symbology: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    kind: LabelKind = field(default=LabelKind.POSITION, init=False)

    def __post_init__(self) -> None:
        if not (self.position_id or "").strip():
            raise ValueError("NormalizedPositionLabel.position_id is required")
        if not (self.raw_payload or "").strip():
            raise ValueError("NormalizedPositionLabel.raw_payload is required")


NormalizedLabel = NormalizedItemLabel | NormalizedPositionLabel


@dataclass(frozen=True)
class LabelValidationResult:
    """Non-exceptional validation outcome."""

    status: LabelValidationStatus
    label: NormalizedLabel | None = None
    error_code: str | None = None
    detail: str | None = None
    profile_source: LabelProfileSource | None = None
    label_kind: LabelKind | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def valid(
        cls,
        label: NormalizedLabel,
        *,
        profile_source: LabelProfileSource,
        label_kind: LabelKind,
        diagnostics: dict[str, Any] | None = None,
    ) -> LabelValidationResult:
        return cls(
            status=LabelValidationStatus.VALID,
            label=label,
            profile_source=profile_source,
            label_kind=label_kind,
            diagnostics=diagnostics or {},
        )

    @classmethod
    def invalid(
        cls,
        *,
        error_code: str,
        detail: str | None = None,
        profile_source: LabelProfileSource | None = None,
        label_kind: LabelKind | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> LabelValidationResult:
        return cls(
            status=LabelValidationStatus.INVALID,
            error_code=error_code,
            detail=detail,
            profile_source=profile_source,
            label_kind=label_kind,
            diagnostics=diagnostics or {},
        )

    @classmethod
    def not_applicable(
        cls,
        *,
        detail: str | None = None,
        profile_source: LabelProfileSource | None = None,
        label_kind: LabelKind | None = None,
    ) -> LabelValidationResult:
        return cls(
            status=LabelValidationStatus.NOT_APPLICABLE,
            error_code=LabelValidationErrorCode.NOT_OUR_FORMAT.value,
            detail=detail,
            profile_source=profile_source,
            label_kind=label_kind,
        )
