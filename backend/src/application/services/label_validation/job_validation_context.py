"""Build job-scoped LabelValidationContext from immutable engine_params snapshot."""

from __future__ import annotations

import logging
from typing import Any

from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.application.services.label_validation.label_validation_service import (
    LabelProfileConfigurationError,
    validate_extraction_configuration_for_code_scan,
)
from src.domain.client_supplier.extraction_profile import ExtractionProfileConfiguration
from src.domain.label_profiles.entities import ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation.context import LabelValidationContext

logger = logging.getLogger(__name__)


def _identification_block(job_engine_params: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(job_engine_params, dict):
        return {}
    ident = job_engine_params.get("identification_execution")
    return ident if isinstance(ident, dict) else {}


def load_resolved_label_profiles_from_job(
    job_engine_params: dict[str, Any] | None,
) -> ResolvedLabelProfiles | None:
    """Return Phase 1 snapshot or None for legacy jobs (no label_profiles)."""
    block = _identification_block(job_engine_params)
    raw = block.get("label_profiles")
    if not isinstance(raw, dict):
        return None
    return ResolvedLabelProfiles.from_snapshot_dict(raw)


def _configuration_from_extraction_snapshot(
    snap: dict[str, Any] | None,
) -> ExtractionProfileConfiguration | None:
    if not isinstance(snap, dict):
        return None
    raw_cfg = snap.get("configuration")
    if raw_cfg is None:
        return None
    try:
        config = parse_extraction_configuration(raw_cfg)
    except ExtractionProfileConfigurationError as exc:
        raise LabelProfileConfigurationError(exc.code, exc.message) from exc
    validate_extraction_configuration_for_code_scan(config)
    return config


def _embedded_kind_configuration(
    *,
    label_profiles_block: dict[str, Any],
    kind: LabelKind,
) -> ExtractionProfileConfiguration | None:
    """Load configuration embedded under label_profiles.{item|position}.configuration."""
    key = "item" if kind is LabelKind.ITEM else "position"
    kind_raw = label_profiles_block.get(key)
    if not isinstance(kind_raw, dict):
        return None
    if kind_raw.get("source") != LabelProfileSource.SUPPLIER.value:
        return None
    if not isinstance(kind_raw.get("configuration"), dict):
        return None
    return _configuration_from_extraction_snapshot(
        {"configuration": kind_raw["configuration"]}
    )


def build_label_validation_context_from_job(
    *,
    job_id: str,
    client_id: str | None,
    job_engine_params: dict[str, Any] | None,
    position_extraction_configuration: ExtractionProfileConfiguration | None = None,
) -> LabelValidationContext:
    """Once-per-job immutable validation context from snapshot (never ``get_active``).

    Prefer embedded ``label_profiles.*.configuration`` (exact profile id/version at
    job start). Legacy ``supplier_extraction_profile.configuration`` is only a
    fallback for older jobs missing the embedded ITEM configuration.
    """
    resolved = load_resolved_label_profiles_from_job(job_engine_params)
    block = _identification_block(job_engine_params)
    label_profiles_raw = block.get("label_profiles")
    label_profiles_raw = label_profiles_raw if isinstance(label_profiles_raw, dict) else {}

    item_config: ExtractionProfileConfiguration | None = None
    position_config = position_extraction_configuration
    if resolved is not None:
        try:
            item_config = _embedded_kind_configuration(
                label_profiles_block=label_profiles_raw, kind=LabelKind.ITEM
            )
            if position_config is None:
                position_config = _embedded_kind_configuration(
                    label_profiles_block=label_profiles_raw, kind=LabelKind.POSITION
                )
        except LabelProfileConfigurationError:
            logger.exception(
                "label_validation.snapshot_config_invalid job_id=%s",
                job_id,
            )
            raise
        # Legacy fallback: older jobs may only have supplier_extraction_profile.
        if item_config is None and resolved.item.source is LabelProfileSource.SUPPLIER:
            legacy_item_snap = block.get("supplier_extraction_profile")
            if isinstance(legacy_item_snap, dict):
                item_config = _configuration_from_extraction_snapshot(legacy_item_snap)

    return LabelValidationContext(
        resolved_profiles=resolved,
        item_extraction_configuration=item_config,
        position_extraction_configuration=position_config,
        job_id=job_id,
        client_id=client_id,
    )


def item_profile_source(context: LabelValidationContext) -> LabelProfileSource:
    if context.resolved_profiles is None:
        return LabelProfileSource.DINAMIC
    return context.resolved_profiles.item.source


def position_profile_source(context: LabelValidationContext) -> LabelProfileSource:
    if context.resolved_profiles is None:
        return LabelProfileSource.DINAMIC
    return context.resolved_profiles.position.source
