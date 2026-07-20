"""Phase 8 — guard against new LEGACY_LLM configurations and effective modes.

Historical retry policy
-----------------------
``RetryAisleJobUseCase`` reuses the original job's immutable identification snapshot
(mode, source, execution strategy, engine_params). Historical LEGACY_LLM jobs **may**
be re-executed via that path; residual creates are recorded as
``legacy_mode_jobs_created_residual_total``.

``StartAisleProcessingUseCase`` (new starts) always resolves the effective mode and
rejects LEGACY_LLM / legacy aliases before persistence. Reading historical jobs remains
allowed.
"""

from __future__ import annotations

import logging
from typing import Any

from src.application.errors import LegacyProcessingModeNotAllowedError
from src.application.services.legacy_processing_metrics import (
    local_metrics_snapshot,
    record_legacy_config_write_blocked,
    record_legacy_job_blocked,
    record_legacy_job_created_residual,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.aisle_identification.resolver import AisleIdentificationModeResolution

logger = logging.getLogger(__name__)

LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION = (
    "LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION"
)

# Explicit policy constant for operators / docs (do not infer from call sites).
HISTORICAL_LEGACY_RETRY_ALLOWED = True


def is_legacy_identification_mode(mode: Any) -> bool:
    if mode is None:
        return False
    if isinstance(mode, AisleIdentificationMode):
        return mode is AisleIdentificationMode.LEGACY_LLM
    raw = str(mode).strip().upper()
    return raw in {
        AisleIdentificationMode.LEGACY_LLM.value,
        "LEGACY_LLM_TEMPORARY",
    }


def reject_legacy_mode_for_new_configuration(
    mode: AisleIdentificationMode | str | None,
    *,
    context: str = "configuration",
) -> None:
    """Block writing LEGACY_LLM onto client/inventory/aisle config.

    Clearing the override (``None``) remains allowed so tenants can inherit
    a non-legacy ancestor or system default after migration.
    """
    if mode is None:
        return
    if not is_legacy_identification_mode(mode):
        return
    raw = mode.value if isinstance(mode, AisleIdentificationMode) else str(mode)
    record_legacy_config_write_blocked(context=context, mode=raw)
    logger.warning(
        "legacy_processing.blocked context=%s mode=%s",
        context,
        raw,
    )
    raise LegacyProcessingModeNotAllowedError(raw, context=context)


def reject_legacy_effective_mode_for_new_job(
    resolution: AisleIdentificationModeResolution,
    *,
    requested_mode: AisleIdentificationMode | str | None = None,
) -> None:
    """Block new job persistence when the *resolved* effective mode is legacy.

    Central enforcement for StartAisleProcessing — covers override, aisle,
    inventory, client, and system-default inheritance.
    """
    if not is_legacy_identification_mode(resolution.effective_mode):
        return
    effective = resolution.effective_mode.value
    source = (
        resolution.source.value
        if isinstance(resolution.source, AisleIdentificationModeSource)
        else str(resolution.source)
    )
    requested = None
    if requested_mode is not None:
        requested = (
            requested_mode.value
            if isinstance(requested_mode, AisleIdentificationMode)
            else str(requested_mode)
        )
    record_legacy_job_blocked(
        requested_mode=requested,
        effective_mode=effective,
        resolution_source=source,
    )
    logger.warning(
        "legacy_processing.effective_mode_blocked effective_mode=%s "
        "resolution_source=%s requested_mode=%s",
        effective,
        source,
        requested or "null",
    )
    raise LegacyProcessingModeNotAllowedError(
        effective,
        context=f"job_start:{source}",
    )


def reject_legacy_mode_for_new_job(
    mode: AisleIdentificationMode | str | None,
) -> None:
    """Block an explicit LEGACY override on new job start.

    Prefer ``reject_legacy_effective_mode_for_new_job`` after full resolution;
    this helper remains for callers that only have the override value.
    """
    if mode is None or not is_legacy_identification_mode(mode):
        return
    raw = mode.value if isinstance(mode, AisleIdentificationMode) else str(mode)
    record_legacy_job_blocked(
        requested_mode=raw,
        effective_mode=raw,
        resolution_source=AisleIdentificationModeSource.REQUEST.value,
    )
    logger.warning("legacy_processing.job_override_blocked mode=%s", raw)
    raise LegacyProcessingModeNotAllowedError(raw, context="job_start")


def note_historical_legacy_retry_created(
    *,
    identification_mode: AisleIdentificationMode | str,
    identification_mode_source: AisleIdentificationModeSource | str,
) -> None:
    """Record residual LEGACY materialization from historical retry (allowed)."""
    if not is_legacy_identification_mode(identification_mode):
        return
    mode = (
        identification_mode.value
        if isinstance(identification_mode, AisleIdentificationMode)
        else str(identification_mode)
    )
    source = (
        identification_mode_source.value
        if isinstance(identification_mode_source, AisleIdentificationModeSource)
        else str(identification_mode_source)
    )
    record_legacy_job_created_residual(
        effective_mode=mode,
        resolution_source=source,
        path="historical_retry",
    )


def legacy_usage_metrics_snapshot() -> dict[str, int]:
    """Process-local snapshot (debug). Prefer structured logs / SQL across replicas."""
    return local_metrics_snapshot()


__all__ = [
    "HISTORICAL_LEGACY_RETRY_ALLOWED",
    "LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION",
    "LegacyProcessingModeNotAllowedError",
    "is_legacy_identification_mode",
    "legacy_usage_metrics_snapshot",
    "note_historical_legacy_retry_created",
    "reject_legacy_effective_mode_for_new_job",
    "reject_legacy_mode_for_new_configuration",
    "reject_legacy_mode_for_new_job",
]
