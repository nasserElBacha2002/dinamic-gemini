"""Parse DINAMIC_POSITION payloads without repository access (Phase 3)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.domain.aisle_location.label_entities import (
    POSITIONING_LABEL_PAYLOAD_VERSION_V1,
    POSITIONING_LABEL_PAYLOAD_VERSION_V2,
    POSITIONING_LABEL_TYPE,
)
from src.domain.aisle_location.payload import payload_sha256, validate_positioning_payload
from src.domain.position_label_detection.entities import PositionLabelDetectionStatus

_SUPPORTED_POSITION_PAYLOAD_VERSIONS = frozenset(
    {
        POSITIONING_LABEL_PAYLOAD_VERSION_V1,
        POSITIONING_LABEL_PAYLOAD_VERSION_V2,
    }
)


@dataclass(frozen=True)
class ParsedPositionLabelPayload:
    status: PositionLabelDetectionStatus
    payload: dict[str, Any] | None = None
    label_id: str | None = None
    version: int | None = None
    key_version: int | None = None
    signature: str | None = None
    payload_hash: str | None = None
    detail: str | None = None


_LEGACY_KEYS = frozenset(
    {
        "inventory_id",
        "aisle_id",
        "job_id",
        "session_id",
        "result_id",
        "position_id",  # aisle-scoped legacy — unsupported for Phase 3 client path
    }
)


class PositionLabelPayloadParser:
    def __init__(
        self,
        *,
        max_payload_bytes: int,
        supported_versions: frozenset[int] | None = None,
        # Deprecated alias kept for call sites that pinned a single version.
        supported_version: int | None = None,
    ) -> None:
        self._max_payload_bytes = max(256, int(max_payload_bytes))
        if supported_versions is not None:
            self._supported_versions = frozenset(int(v) for v in supported_versions)
        elif supported_version is not None:
            self._supported_versions = frozenset({int(supported_version)})
        else:
            self._supported_versions = _SUPPORTED_POSITION_PAYLOAD_VERSIONS

    def parse(self, raw_value: str) -> ParsedPositionLabelPayload:
        text = (raw_value or "").strip()
        if not text:
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.INVALID_JSON,
                detail="empty payload",
            )
        raw_bytes = text.encode("utf-8")
        if len(raw_bytes) > self._max_payload_bytes:
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.PAYLOAD_TOO_LARGE,
                detail=f"payload exceeds {self._max_payload_bytes} bytes",
            )
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.INVALID_JSON,
                detail="invalid JSON",
            )
        if not isinstance(parsed, dict):
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.INVALID_JSON,
                detail="payload must be a JSON object",
            )
        legacy = sorted(k for k in _LEGACY_KEYS if k in parsed)
        if legacy:
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.UNSUPPORTED_LEGACY_PAYLOAD,
                payload=parsed,
                detail="unsupported legacy fields: " + ",".join(legacy),
            )
        type_value = parsed.get("type")
        if type_value != POSITIONING_LABEL_TYPE:
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.INVALID_TYPE,
                payload=parsed,
                detail=f"expected type={POSITIONING_LABEL_TYPE}",
            )
        try:
            version = int(parsed.get("version", -1))
        except (TypeError, ValueError):
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.UNSUPPORTED_VERSION,
                payload=parsed,
                detail="version must be an integer",
            )
        if version not in self._supported_versions:
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.UNSUPPORTED_VERSION,
                payload=parsed,
                version=version,
                signature=_optional_signature(parsed),
                detail=f"unsupported version={version}",
            )
        label_id = parsed.get("label_id")
        if not isinstance(label_id, str) or not label_id.strip():
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.MISSING_LABEL_ID,
                payload=parsed,
                version=version,
                signature=_optional_signature(parsed),
                detail="label_id required",
            )
        signature = parsed.get("signature")
        if signature is None or (isinstance(signature, str) and not signature.strip()):
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.MISSING_SIGNATURE,
                payload=parsed,
                label_id=label_id.strip(),
                version=version,
                detail="signature required",
            )
        if not isinstance(signature, str):
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.MISSING_SIGNATURE,
                payload=parsed,
                label_id=label_id.strip(),
                version=version,
                detail="signature must be a string",
            )
        key_version: int | None = None
        if "key_version" in parsed:
            try:
                key_version = int(parsed["key_version"])
                if key_version < 1:
                    raise ValueError("key_version < 1")
            except (TypeError, ValueError):
                return ParsedPositionLabelPayload(
                    status=PositionLabelDetectionStatus.UNKNOWN_KEY_VERSION,
                    payload=parsed,
                    label_id=label_id.strip(),
                    version=version,
                    signature=signature.strip(),
                    detail="invalid key_version",
                )
        try:
            validate_positioning_payload(parsed)
        except ValueError as exc:
            return ParsedPositionLabelPayload(
                status=PositionLabelDetectionStatus.INVALID_TYPE,
                payload=parsed,
                label_id=label_id.strip(),
                version=version,
                key_version=key_version,
                signature=signature.strip(),
                detail=str(exc),
            )
        return ParsedPositionLabelPayload(
            status=PositionLabelDetectionStatus.VALID,
            payload=parsed,
            label_id=label_id.strip(),
            version=version,
            key_version=key_version,
            signature=signature.strip(),
            payload_hash=payload_sha256(parsed),
        )


def _optional_signature(parsed: dict[str, Any]) -> str | None:
    signature = parsed.get("signature")
    if isinstance(signature, str) and signature.strip():
        return signature.strip()
    return None
