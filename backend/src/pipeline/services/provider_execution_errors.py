"""
Phase 4.4 — Provider adapter / manifest execution error taxonomy.

Raised before remote provider calls when serialization or manifest parity fails.
"""

from __future__ import annotations

from typing import Any


class ProviderImageExecutionError(ValueError):
    """Adapter-boundary failure for manifest-aligned provider image execution."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        job_id: str | None = None,
        provider: str | None = None,
        manifest_entry_id: str | None = None,
        role: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.job_id = job_id
        self.provider = provider
        self.manifest_entry_id = manifest_entry_id
        self.role = role
        self.details = dict(details) if details else {}
        super().__init__(f"[{code}] {message}")

    def to_details(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, **self.details}
        if self.job_id:
            out["job_id"] = self.job_id
        if self.provider:
            out["provider"] = self.provider
        if self.manifest_entry_id:
            out["manifest_entry_id"] = self.manifest_entry_id
        if self.role:
            out["role"] = self.role
        return out


# Stable error codes (worker / adapter observability).
PROVIDER_IMAGE_MANIFEST_MISMATCH = "PROVIDER_IMAGE_MANIFEST_MISMATCH"
PROVIDER_IMAGE_SERIALIZATION_FAILED = "PROVIDER_IMAGE_SERIALIZATION_FAILED"
PROVIDER_IMAGE_UNSUPPORTED_FORMAT = "PROVIDER_IMAGE_UNSUPPORTED_FORMAT"
PROVIDER_IMAGE_LIMIT_EXCEEDED = "PROVIDER_IMAGE_LIMIT_EXCEEDED"
PROVIDER_IMAGE_RESOURCE_MISSING = "PROVIDER_IMAGE_RESOURCE_MISSING"
