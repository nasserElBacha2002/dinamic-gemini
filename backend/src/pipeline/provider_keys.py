"""Pipeline provider key normalization and explicit job-provider resolution (Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class UnknownPipelineProviderKeyError(LookupError):
    """Raised when an explicit provider key is not registered."""


class InactivePipelineProviderKeyError(LookupError):
    """Raised when an explicit job provider is registered but inactive (deprecated)."""


@dataclass(frozen=True)
class ResolvedPipelineProviderKey:
    """Result of provider key resolution with optional explicit request audit fields."""

    resolved_key: str
    #: Non-empty when the caller passed an explicit provider (e.g. job.provider_name).
    requested_key: str | None = None
    #: How the resolved key was chosen (audit / ops).
    resolution_source: str = "settings_default"

    @property
    def remapped(self) -> bool:
        """True when requested and resolved keys differ (should not happen for explicit jobs)."""
        if not self.requested_key:
            return False
        return self.requested_key.strip().lower() != self.resolved_key.strip().lower()


def resolve_pipeline_provider_key(
    provider_name: str | None,
    settings: Any,
) -> ResolvedPipelineProviderKey:
    """
    Resolve the logical pipeline provider key for a run.

    **Explicit job provider** (non-empty ``provider_name``):
    - Must be a registered key; unknown → :class:`UnknownPipelineProviderKeyError`.
    - Must be active; inactive/deprecated → :class:`InactivePipelineProviderKeyError`.
    - Never silently remapped to another vendor.

    **Settings default** (empty ``provider_name``):
    - Uses ``settings.llm_provider``.
    - When that default is an inactive registered key (e.g. legacy ``deepseek``), remaps to
      ``gemini`` for backward-compatible deployments — this is **not** runtime failover and does
      not apply to explicit job providers.
    """
    from src.pipeline.providers.definitions import (
        is_pipeline_provider_active,
        pipeline_provider_spec,
    )

    raw = (provider_name or "").strip().lower()
    if raw:
        spec = pipeline_provider_spec(raw)
        if spec is None:
            raise UnknownPipelineProviderKeyError(
                f"Unknown pipeline provider {raw!r}."
            )
        if not spec.is_active:
            raise InactivePipelineProviderKeyError(
                f"Pipeline provider {raw!r} is inactive or deprecated."
            )
        return ResolvedPipelineProviderKey(
            resolved_key=raw,
            requested_key=raw,
            resolution_source="explicit_job_provider",
        )

    sp = str(getattr(settings, "llm_provider", "gemini") or "gemini").strip().lower()
    if is_pipeline_provider_active(sp):
        return ResolvedPipelineProviderKey(
            resolved_key=sp,
            requested_key=None,
            resolution_source="settings_default",
        )
    if pipeline_provider_spec(sp) is not None:
        return ResolvedPipelineProviderKey(
            resolved_key="gemini",
            requested_key=None,
            resolution_source="settings_default_remapped",
        )
    return ResolvedPipelineProviderKey(
        resolved_key=sp,
        requested_key=None,
        resolution_source="settings_default",
    )


def normalize_pipeline_provider_key(
    provider_name: str | None,
    settings: Any,
) -> str:
    """Return resolved provider key; see :func:`resolve_pipeline_provider_key`."""
    return resolve_pipeline_provider_key(provider_name, settings).resolved_key
