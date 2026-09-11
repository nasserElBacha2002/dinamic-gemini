"""Canonical content fingerprint for preliminary detection idempotency."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _norm_str(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _norm_upper(value: str | None) -> str | None:
    text = _norm_str(value)
    return text.upper() if text else None


def _norm_sha(value: str | None) -> str | None:
    text = _norm_str(value)
    if not text:
        return None
    if text.lower().startswith("sha256:"):
        return "sha256:" + text.split(":", 1)[1].lower()
    return text.lower()


def _norm_detected_at(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        dt = value.replace(tzinfo=timezone.utc)
    else:
        dt = value.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PreliminaryDetectionContent:
    """Normalized fields compared for idempotency (same draft or secondary key)."""

    draft_id: str
    asset_id: str
    client_file_id: str
    status: str
    internal_code: str | None
    quantity: int | None
    quantity_status: str | None
    detected_format: str | None
    detected_symbology: str | None
    candidate_count: int
    parser_version: str
    detector_version: str
    prepared_asset_sha256: str
    payload_hash: str | None
    schema_version: str
    detected_at: str | None
    position_evidence: tuple[Any, ...] | None

    def fingerprint_without_draft_id(self) -> tuple[Any, ...]:
        """Secondary-key content compare excludes draft_id (identity may differ)."""
        return (
            self.asset_id,
            self.client_file_id,
            self.status,
            self.internal_code,
            self.quantity,
            self.quantity_status,
            self.detected_format,
            self.detected_symbology,
            self.candidate_count,
            self.parser_version,
            self.detector_version,
            self.prepared_asset_sha256,
            self.payload_hash,
            self.schema_version,
            self.detected_at,
            self.position_evidence,
        )

    def fingerprint(self) -> tuple[Any, ...]:
        return (self.draft_id, *self.fingerprint_without_draft_id())


class PreliminaryDetectionContentCanonicalizer:
    @staticmethod
    def from_command_like(obj: Any) -> PreliminaryDetectionContent:
        detected_at = getattr(obj, "detected_at", None)
        position_reference = getattr(obj, "position_reference", None)
        position_evidence: tuple[Any, ...] | None
        if position_reference is not None:
            signature = getattr(position_reference, "signature", None)
            captured_at = getattr(position_reference, "captured_at", None)
            position_evidence = (
                int(getattr(position_reference, "payload_version", 0) or 0),
                _norm_str(getattr(position_reference, "local_recognition_id", None)),
                _norm_str(getattr(position_reference, "raw_code", None)),
                _norm_upper(getattr(position_reference, "normalized_code", None)),
                _norm_str(getattr(position_reference, "remote_position_id", None)),
                _norm_str(getattr(position_reference, "remote_position_label_id", None)),
                _norm_upper(getattr(position_reference, "source", None)),
                _norm_str(getattr(position_reference, "profile_id", None)),
                getattr(position_reference, "profile_version", None),
                _norm_str(getattr(position_reference, "client_supplier_id", None)),
                getattr(signature, "present", None),
                _norm_upper(getattr(signature, "verification", None)),
                _norm_detected_at(captured_at)
                if isinstance(captured_at, datetime)
                else _norm_str(captured_at),
            )
        else:
            local_recognition_id = getattr(obj, "position_local_recognition_id", None)
            position_evidence = (
                (
                    2,
                    _norm_str(local_recognition_id),
                    _norm_str(getattr(obj, "position_raw_code", None)),
                    _norm_upper(getattr(obj, "position_claimed_normalized_code", None)),
                    _norm_str(getattr(obj, "position_claimed_remote_id", None)),
                    _norm_str(getattr(obj, "position_claimed_remote_label_id", None)),
                    _norm_upper(getattr(obj, "position_source", None)),
                    _norm_str(getattr(obj, "position_profile_id", None)),
                    getattr(obj, "position_profile_version", None),
                    _norm_str(getattr(obj, "position_client_supplier_id", None)),
                    getattr(obj, "position_signature_present", None),
                    _norm_upper(getattr(obj, "position_signature_verification", None)),
                    _norm_detected_at(getattr(obj, "position_captured_at", None)),
                )
                if local_recognition_id is not None
                else None
            )
        schema = _norm_str(getattr(obj, "schema_version", None)) or "1"
        if schema.lower() == "v1":
            schema = "1"
        return PreliminaryDetectionContent(
            draft_id=(_norm_str(getattr(obj, "draft_id", None)) or "").strip(),
            asset_id=(_norm_str(getattr(obj, "asset_id", None)) or "").strip(),
            client_file_id=(_norm_str(getattr(obj, "client_file_id", None)) or "").strip(),
            status=_norm_upper(getattr(obj, "status", None)) or "",
            internal_code=_norm_str(getattr(obj, "internal_code", None)),
            quantity=getattr(obj, "quantity", None),
            quantity_status=_norm_upper(getattr(obj, "quantity_status", None)),
            detected_format=_norm_upper(getattr(obj, "detected_format", None)),
            detected_symbology=_norm_upper(getattr(obj, "detected_symbology", None)),
            candidate_count=int(getattr(obj, "candidate_count", 0) or 0),
            parser_version=_norm_str(getattr(obj, "parser_version", None)) or "",
            detector_version=_norm_str(getattr(obj, "detector_version", None)) or "",
            prepared_asset_sha256=_norm_sha(getattr(obj, "prepared_asset_sha256", None)) or "",
            payload_hash=_norm_sha(getattr(obj, "payload_hash", None)),
            schema_version=schema,
            detected_at=_norm_detected_at(detected_at)
            if isinstance(detected_at, datetime)
            else _norm_str(detected_at),
            position_evidence=position_evidence,
        )

    @staticmethod
    def same_for_draft_id(a: PreliminaryDetectionContent, b: PreliminaryDetectionContent) -> bool:
        return a.fingerprint() == b.fingerprint()

    @staticmethod
    def same_payload(a: PreliminaryDetectionContent, b: PreliminaryDetectionContent) -> bool:
        return a.fingerprint_without_draft_id() == b.fingerprint_without_draft_id()
