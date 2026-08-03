"""HMAC-SHA256 signing for DINAMIC_POSITION payloads (backend-only secrets)."""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass

from src.domain.aisle_location.payload import (
    canonicalize_positioning_payload_for_signing,
    validate_positioning_payload,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositioningLabelSigningConfig:
    """Resolved signing material. Secrets never leave the backend process."""

    secret: str | None
    key_version: int = 1
    previous_secrets: tuple[tuple[int, str], ...] = ()
    required: bool = False


class PositioningLabelSigningError(ValueError):
    """Raised when signing is required but misconfigured."""


class PositioningLabelSigningService:
    def __init__(self, config: PositioningLabelSigningConfig) -> None:
        self._config = config

    @property
    def key_version(self) -> int:
        return int(self._config.key_version)

    @property
    def can_sign(self) -> bool:
        return bool((self._config.secret or "").strip())

    @property
    def required(self) -> bool:
        return bool(self._config.required)

    def sign_payload(self, payload: dict) -> dict:
        """Return a new payload dict with key_version + signature applied."""
        validate_positioning_payload(payload)
        secret = (self._config.secret or "").strip()
        if not secret:
            if self._config.required:
                raise PositioningLabelSigningError(
                    "POSITIONING_LABEL_HMAC_SECRET is required but not configured"
                )
            return dict(payload)
        working = {k: v for k, v in payload.items() if k != "signature"}
        working["key_version"] = int(self._config.key_version)
        message = canonicalize_positioning_payload_for_signing(working).encode("utf-8")
        digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        working["signature"] = digest
        validate_positioning_payload(working)
        return working

    def verify_payload(self, payload: dict) -> bool:
        validate_positioning_payload(payload)
        signature = payload.get("signature")
        if not isinstance(signature, str) or not signature.strip():
            return False
        key_version = int(payload.get("key_version") or 0)
        secret = self._secret_for_version(key_version)
        if not secret:
            return False
        working = {k: v for k, v in payload.items() if k != "signature"}
        message = canonicalize_positioning_payload_for_signing(working).encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature.strip())

    def has_secret_for_version(self, key_version: int) -> bool:
        return self._secret_for_version(int(key_version)) is not None

    def _secret_for_version(self, key_version: int) -> str | None:
        if key_version == int(self._config.key_version):
            secret = (self._config.secret or "").strip()
            return secret or None
        for ver, sec in self._config.previous_secrets:
            if int(ver) == int(key_version):
                cleaned = (sec or "").strip()
                return cleaned or None
        return None


def parse_previous_secrets(raw: str | None) -> tuple[tuple[int, str], ...]:
    """Parse ``version:secret,version:secret`` (comma-separated)."""
    text = (raw or "").strip()
    if not text:
        return ()
    out: list[tuple[int, str]] = []
    for part in text.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            logger.warning("ignoring malformed POSITIONING_LABEL_HMAC_PREVIOUS_SECRETS entry")
            continue
        ver_s, sec = chunk.split(":", 1)
        try:
            ver = int(ver_s.strip())
        except ValueError:
            logger.warning("ignoring non-integer key version in previous secrets")
            continue
        if ver < 1 or not sec.strip():
            continue
        out.append((ver, sec.strip()))
    return tuple(out)
