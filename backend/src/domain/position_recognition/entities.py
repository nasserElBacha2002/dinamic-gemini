"""Canonical contracts for position recognition and validation.

Recognition and structural validation deliberately do not imply that a durable
position already exists. Persistence/materialization belongs to later phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
    INVALID_FORMAT = "INVALID_FORMAT"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    AMBIGUOUS_CODE = "AMBIGUOUS_CODE"
    PROFILE_NOT_ALLOWED = "PROFILE_NOT_ALLOWED"
    FIELD_CONSTRAINT_VIOLATION = "FIELD_CONSTRAINT_VIOLATION"
    INVALID_CHECKSUM = "INVALID_CHECKSUM"
    SIGNATURE_REQUIRED_BY_LEGACY_POLICY = "SIGNATURE_REQUIRED_BY_LEGACY_POLICY"
    PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY = "PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY"
    INVENTORY_NOT_WRITABLE = "INVENTORY_NOT_WRITABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


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
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalPositionValidationResult:
    status: CanonicalPositionValidationStatus
    recognition: CanonicalPositionRecognition | None = None
    error_code: str | None = None
    existing_position_label_id: str | None = None
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
