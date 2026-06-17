"""
Phase 4.4 — Resolve model-returned evidence identifiers to stable source_image_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.domain.entity import Entity
from src.domain.execution_image_manifest import (
    EVIDENCE_RETURN_IDENTIFIER_FIELD,
    LEGACY_EVIDENCE_RETURN_FIELD,
    ExecutionImageManifest,
    require_manifest_from_composition,
)

WARNING_CONFLICTING_EVIDENCE_IDS = (
    "Conflicting manifest_entry_id and source_image_id were returned."
)


class EvidenceResolutionOutcome(str, Enum):
    MISSING = "missing"
    RESOLVED = "resolved"
    CONFLICT = "conflict"
    INVALID_REFERENCE = "invalid_reference"
    INVALID_UNKNOWN = "invalid_unknown"


@dataclass(frozen=True)
class RawEvidenceIdentifier:
    manifest_entry_id: str | None
    legacy_source_image_id: str | None


@dataclass(frozen=True)
class EvidenceResolutionResult:
    outcome: EvidenceResolutionOutcome
    resolved_source_image_id: str | None = None
    warning: str | None = None


def raw_evidence_from_entity_dict(entity_dict: dict[str, Any]) -> RawEvidenceIdentifier:
    mid = entity_dict.get(EVIDENCE_RETURN_IDENTIFIER_FIELD)
    sid = entity_dict.get(LEGACY_EVIDENCE_RETURN_FIELD)
    return RawEvidenceIdentifier(
        manifest_entry_id=str(mid).strip() if mid is not None and str(mid).strip() else None,
        legacy_source_image_id=str(sid).strip() if sid is not None and str(sid).strip() else None,
    )


def raw_evidence_from_entity(entity: Entity) -> RawEvidenceIdentifier:
    return RawEvidenceIdentifier(
        manifest_entry_id=(
            str(entity.manifest_entry_id).strip()
            if getattr(entity, "manifest_entry_id", None)
            else None
        ),
        legacy_source_image_id=(
            str(entity.source_image_id).strip() if entity.source_image_id else None
        ),
    )


def resolve_raw_evidence_identifier(
    raw: RawEvidenceIdentifier,
    manifest: ExecutionImageManifest,
) -> EvidenceResolutionResult:
    mid = raw.manifest_entry_id
    legacy = raw.legacy_source_image_id

    if not mid and not legacy:
        return EvidenceResolutionResult(outcome=EvidenceResolutionOutcome.MISSING)

    mid_resolved = manifest.resolve_source_image_id(mid) if mid else None
    legacy_resolved = manifest.resolve_source_image_id(legacy) if legacy else None

    if mid and manifest.is_reference_manifest_entry_id(mid):
        return EvidenceResolutionResult(
            outcome=EvidenceResolutionOutcome.INVALID_REFERENCE,
            resolved_source_image_id=mid_resolved,
            warning="Reference manifest entry cannot be used as primary evidence.",
        )

    if mid and not mid_resolved:
        return EvidenceResolutionResult(
            outcome=EvidenceResolutionOutcome.INVALID_UNKNOWN,
            warning=f"Unknown {EVIDENCE_RETURN_IDENTIFIER_FIELD}: {mid}",
        )

    if legacy and not legacy_resolved:
        return EvidenceResolutionResult(
            outcome=EvidenceResolutionOutcome.INVALID_UNKNOWN,
            warning=f"Unknown {LEGACY_EVIDENCE_RETURN_FIELD}: {legacy}",
        )

    if mid and legacy:
        if mid_resolved and legacy_resolved and mid_resolved != legacy_resolved:
            return EvidenceResolutionResult(
                outcome=EvidenceResolutionOutcome.CONFLICT,
                warning=WARNING_CONFLICTING_EVIDENCE_IDS,
            )
        canonical = mid_resolved or legacy_resolved
        return EvidenceResolutionResult(
            outcome=EvidenceResolutionOutcome.RESOLVED,
            resolved_source_image_id=canonical,
        )

    if mid:
        return EvidenceResolutionResult(
            outcome=EvidenceResolutionOutcome.RESOLVED,
            resolved_source_image_id=mid_resolved,
        )

    return EvidenceResolutionResult(
        outcome=EvidenceResolutionOutcome.RESOLVED,
        resolved_source_image_id=legacy_resolved,
    )


def apply_evidence_resolution_to_entities(
    entities: list[Entity],
    *,
    composition: dict[str, Any] | None,
) -> None:
    """Resolve raw evidence fields to canonical source_image_id or pre-mark invalid outcomes."""
    from src.domain.traceability import TraceabilityStatus

    manifest = require_manifest_from_composition(composition)
    if manifest is None:
        return

    for ent in entities:
        raw = raw_evidence_from_entity(ent)
        result = resolve_raw_evidence_identifier(raw, manifest)
        if result.outcome == EvidenceResolutionOutcome.RESOLVED and result.resolved_source_image_id:
            ent.source_image_id = result.resolved_source_image_id
            continue
        if result.outcome == EvidenceResolutionOutcome.MISSING:
            ent.source_image_id = None
            continue
        ent.source_image_id = result.resolved_source_image_id
        ent.traceability_status = TraceabilityStatus.INVALID.value
        ent.traceability_warning = result.warning


# Backward-compatible alias used by entity resolution stage.
normalize_entity_evidence_identifiers = apply_evidence_resolution_to_entities
