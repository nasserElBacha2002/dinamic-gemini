"""Canonical contracts for position recognition and validation.

Recognition and structural validation deliberately do not imply that a durable
position already exists. Persistence/materialization belongs to later phases.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType


class PositionRecognitionSource(str, Enum):
    CODE_SCAN = "CODE_SCAN"
    VISION = "VISION"
    OCR = "OCR"
    TXT = "TXT"
    CSV = "CSV"
    MANUAL = "MANUAL"
    MOBILE = "MOBILE"
    API = "API"


class PositionSignatureVerification(str, Enum):
    MISSING = "MISSING"
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CanonicalPositionValidationStatus(str, Enum):
    VALID_EXISTING = "VALID_EXISTING"
    VALID_UNMATERIALIZED = "VALID_UNMATERIALIZED"
    VALID_PENDING_RESOLUTION = "VALID_PENDING_RESOLUTION"
    INVALID_FORMAT = "INVALID_FORMAT"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    SIGNATURE_VALIDATION_SKIPPED = "SIGNATURE_VALIDATION_SKIPPED"
    AMBIGUOUS_CODE = "AMBIGUOUS_CODE"
    PROFILE_NOT_ALLOWED = "PROFILE_NOT_ALLOWED"
    FIELD_CONSTRAINT_VIOLATION = "FIELD_CONSTRAINT_VIOLATION"
    INVALID_CHECKSUM = "INVALID_CHECKSUM"
    SIGNATURE_REQUIRED_BY_LEGACY_POLICY = "SIGNATURE_REQUIRED_BY_LEGACY_POLICY"
    PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY = "PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class PositionResolutionStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    EXISTING = "EXISTING"
    NOT_FOUND = "NOT_FOUND"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class PositionSignatureEvidence:
    present: bool
    verification: PositionSignatureVerification
    key_version: int | None = None

    @property
    def verified(self) -> bool:
        return self.verification is PositionSignatureVerification.VERIFIED


@dataclass(frozen=True)
class CanonicalPositionRecognition:
    """Validated semantic position identity, independent from persistence IDs."""

    raw_code: str
    normalized_code: str
    source: PositionRecognitionSource
    pallet: str | None = None
    side: str | None = None
    level: int | None = None
    marker_index: int | None = None
    marker_total: int | None = None
    profile_id: str | None = None
    profile_version: int | None = None
    client_supplier_id: str | None = None
    signature: PositionSignatureEvidence = field(
        default_factory=lambda: PositionSignatureEvidence(
            present=False,
            verification=PositionSignatureVerification.NOT_APPLICABLE,
        )
    )
    evidence: Mapping[str, str | int | float | bool | None] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if any(
            value is not None and not isinstance(value, (str, int, float, bool))
            for value in self.evidence.values()
        ):
            raise ValueError("canonical position evidence values must be immutable scalars")
        object.__setattr__(
            self,
            "evidence",
            MappingProxyType(dict(self.evidence)),
        )


@dataclass(frozen=True)
class CanonicalPositionValidationResult:
    status: CanonicalPositionValidationStatus
    recognition: CanonicalPositionRecognition | None = None
    error_code: str | None = None
    existing_position_label_id: str | None = None
    resolution_status: PositionResolutionStatus = PositionResolutionStatus.NOT_EVALUATED
    policy_rejection: bool = False
    detail: str | None = None

    @property
    def structurally_valid(self) -> bool:
        return self.recognition is not None

    @property
    def operationally_accepted(self) -> bool:
        return self.status in {
            CanonicalPositionValidationStatus.VALID_EXISTING,
            CanonicalPositionValidationStatus.VALID_UNMATERIALIZED,
        }
