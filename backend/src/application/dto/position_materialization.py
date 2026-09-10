"""Application inputs for physical-position materialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from src.application.dto.access_principal import AccessPrincipal
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
    PositionSignatureVerification,
)

POSITION_MATERIALIZATION_FINGERPRINT_VERSION = 1
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class FingerprintSignatureV1:
    present: bool
    verification: str
    key_version: int | None


@dataclass(frozen=True)
class FingerprintV1:
    """Stable semantic payload for materialization idempotency."""

    version: int
    client_id: str
    inventory_id: str
    aisle_id: str
    capture_id: str | None
    raw_code: str | None
    raw_payload_hash: str | None
    raw_payload_length: int | None
    raw_hash_algorithm: str | None
    display_code: str | None
    normalized_code: str
    source: str
    client_supplier_id: str | None
    profile_id: str | None
    profile_version: int | None
    pallet: str | None
    side: str | None
    level: int | None
    marker_index: int | None
    marker_total: int | None
    signature: FingerprintSignatureV1

    def payload(self) -> dict[str, JsonValue]:
        return {
            "version": self.version,
            "client_id": self.client_id,
            "inventory_id": self.inventory_id,
            "aisle_id": self.aisle_id,
            "capture_id": self.capture_id,
            "raw_code": self.raw_code,
            "raw_payload_hash": self.raw_payload_hash,
            "raw_payload_length": self.raw_payload_length,
            "raw_hash_algorithm": self.raw_hash_algorithm,
            "display_code": self.display_code,
            "normalized_code": self.normalized_code,
            "source": self.source,
            "client_supplier_id": self.client_supplier_id,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "pallet": self.pallet,
            "side": self.side,
            "level": self.level,
            "marker_index": self.marker_index,
            "marker_total": self.marker_total,
            "signature": {
                "present": self.signature.present,
                "verification": self.signature.verification,
                "key_version": self.signature.key_version,
            },
        }


@dataclass(frozen=True)
class MaterializePositionCommand:
    recognition: CanonicalPositionRecognition
    inventory_id: str
    aisle_id: str
    principal: AccessPrincipal
    idempotency_key: str
    capture_id: str | None = None
    safe_raw_evidence: SafeRawCodeEvidence | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.recognition, CanonicalPositionRecognition):
            raise TypeError("recognition must be CanonicalPositionRecognition")
        if not isinstance(self.principal, AccessPrincipal):
            raise TypeError("principal must be AccessPrincipal")


@dataclass(frozen=True)
class SafeRawCodeEvidence:
    """Privacy-safe substitute when the original CODE_SCAN payload is not retained."""

    payload_hash: str
    display_code: str
    utf8_length: int | None = None
    hash_algorithm: str = "sha256-utf8-v1"


def build_fingerprint_v1(command: MaterializePositionCommand) -> FingerprintV1:
    """Build a canonical payload, rejecting malformed functional values."""
    recognition = command.recognition
    client_id = command.principal.client_id
    if not isinstance(client_id, str) or not client_id:
        raise ValueError("principal.client_id must be a non-empty string")
    string_fields = {
        "inventory_id": command.inventory_id,
        "aisle_id": command.aisle_id,
        "normalized_code": recognition.normalized_code,
    }
    if command.capture_id is not None:
        string_fields["capture_id"] = command.capture_id
    if recognition.raw_code is not None:
        string_fields["raw_code"] = recognition.raw_code
    optional_strings = {
        "client_supplier_id": recognition.client_supplier_id,
        "profile_id": recognition.profile_id,
        "pallet": recognition.pallet,
        "side": recognition.side,
    }
    for name, value in {**string_fields, **optional_strings}.items():
        if value is not None and not isinstance(value, str):
            raise TypeError(f"{name} must be a string")
    if not isinstance(recognition.source, PositionRecognitionSource):
        raise TypeError("recognition.source must be PositionRecognitionSource")
    if not isinstance(recognition.signature.verification, PositionSignatureVerification):
        raise TypeError("recognition.signature.verification must be PositionSignatureVerification")
    if not isinstance(recognition.signature.present, bool):
        raise TypeError("recognition.signature.present must be bool")
    integer_fields = (
        recognition.profile_version,
        recognition.level,
        recognition.marker_index,
        recognition.marker_total,
        recognition.signature.key_version,
    )
    if any(
        value is not None and (not isinstance(value, int) or isinstance(value, bool))
        for value in integer_fields
    ):
        raise TypeError("fingerprint numeric fields must be integers")
    return FingerprintV1(
        version=POSITION_MATERIALIZATION_FINGERPRINT_VERSION,
        client_id=client_id,
        inventory_id=command.inventory_id,
        aisle_id=command.aisle_id,
        capture_id=command.capture_id,
        raw_code=recognition.raw_code,
        raw_payload_hash=(
            command.safe_raw_evidence.payload_hash if command.safe_raw_evidence else None
        ),
        raw_payload_length=(
            command.safe_raw_evidence.utf8_length if command.safe_raw_evidence else None
        ),
        raw_hash_algorithm=(
            command.safe_raw_evidence.hash_algorithm if command.safe_raw_evidence else None
        ),
        display_code=(
            command.safe_raw_evidence.display_code if command.safe_raw_evidence else None
        ),
        normalized_code=recognition.normalized_code,
        source=recognition.source.value,
        client_supplier_id=recognition.client_supplier_id,
        profile_id=recognition.profile_id,
        profile_version=recognition.profile_version,
        pallet=recognition.pallet,
        side=recognition.side,
        level=recognition.level,
        marker_index=recognition.marker_index,
        marker_total=recognition.marker_total,
        signature=FingerprintSignatureV1(
            present=recognition.signature.present,
            verification=recognition.signature.verification.value,
            key_version=recognition.signature.key_version,
        ),
    )
