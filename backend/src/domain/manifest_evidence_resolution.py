"""
Phase 4.5 — Manifest-aware evidence identifier resolution.

Central resolver for provider-returned ``manifest_entry_id`` and legacy ``source_image_id``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.domain.entity import Entity
from src.domain.execution_image_manifest import (
    EVIDENCE_RETURN_IDENTIFIER_FIELD,
    LEGACY_EVIDENCE_RETURN_FIELD,
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageManifestError,
    ExecutionImageRole,
    composition_has_execution_image_manifest,
    require_manifest_from_composition,
)
from src.domain.traceability import TraceabilityStatus

WARNING_CONFLICTING_EVIDENCE_IDS = (
    "Provider returned conflicting manifest_entry_id and source_image_id."
)
WARNING_MISSING_EVIDENCE_ID = "Provider did not return an evidence image identifier."
WARNING_UNKNOWN_MANIFEST_ENTRY_ID = "Provider returned an unknown manifest_entry_id."
WARNING_REFERENCE_AS_EVIDENCE = "Provider returned a reference image as evidence."
WARNING_UNKNOWN_SOURCE_IMAGE_ID = "Provider returned an unknown source_image_id."
WARNING_REFERENCE_SOURCE_ID = "Provider returned a reference source_image_id as evidence."
WARNING_MALFORMED_MANIFEST_ENTRY_ID = "Provider returned a malformed manifest_entry_id."
WARNING_MALFORMED_EVIDENCE_IDS = "Provider returned malformed evidence identifiers."
WARNING_UNKNOWN_LEGACY_SOURCE = (
    "Provider returned conflicting or unknown legacy source_image_id."
)
WARNING_MANIFEST_UNAVAILABLE = (
    "Canonical execution manifest was unavailable; evidence could not be validated."
)
WARNING_MANIFEST_INVALID = (
    "Canonical execution manifest was invalid; evidence could not be validated."
)
WARNING_MERGE_EVIDENCE_CONFLICT = (
    "Merged entities had conflicting evidence identifiers."
)
WARNING_MERGE_MULTIPLE_VALID_SOURCES = (
    "Merged entities referenced different valid evidence images; kept first deterministically."
)


class EvidenceResolutionOutcome(str, Enum):
    MISSING = "missing"
    RESOLVED = "resolved"
    CONFLICT = "conflict"
    INVALID_REFERENCE = "invalid_reference"
    INVALID_UNKNOWN = "invalid_unknown"
    INVALID_MALFORMED = "invalid_malformed"
    MANIFEST_UNAVAILABLE = "manifest_unavailable"
    MANIFEST_INVALID = "manifest_invalid"
    LEGACY_DEFERRED = "legacy_deferred"


@dataclass(frozen=True)
class RawEvidenceIdentifier:
    manifest_entry_id: str | None
    legacy_source_image_id: str | None


@dataclass(frozen=True)
class EvidenceResolutionResult:
    outcome: EvidenceResolutionOutcome
    traceability_status: str | None
    raw_manifest_entry_id: str | None = None
    raw_source_image_id: str | None = None
    resolved_manifest_entry_id: str | None = None
    resolved_source_image_id: str | None = None
    role: ExecutionImageRole | None = None
    traceability_warning: str | None = None

    @property
    def warning(self) -> str | None:
        return self.traceability_warning

    @property
    def resolved_source_image_id_compat(self) -> str | None:
        return self.resolved_source_image_id


_PRIMARY_MANIFEST_ENTRY_ID_RE = re.compile(r"^IMG_\d+$")
_REFERENCE_MANIFEST_ENTRY_ID_RE = re.compile(r"^REF_\d+$")


def is_well_formed_manifest_entry_id(value: str) -> bool:
    """Case-sensitive manifest entry ID format (IMG_nnn / REF_nnn)."""
    stripped = (value or "").strip()
    if not stripped:
        return False
    return bool(
        _PRIMARY_MANIFEST_ENTRY_ID_RE.match(stripped)
        or _REFERENCE_MANIFEST_ENTRY_ID_RE.match(stripped)
    )


def is_malformed_manifest_entry_id(value: str) -> bool:
    stripped = (value or "").strip()
    if not stripped:
        return False
    return not is_well_formed_manifest_entry_id(stripped)


def _is_reference_manifest_entry_id(value: str) -> bool:
    return bool(_REFERENCE_MANIFEST_ENTRY_ID_RE.match((value or "").strip()))


def _is_primary_manifest_entry_id(value: str) -> bool:
    return bool(_PRIMARY_MANIFEST_ENTRY_ID_RE.match((value or "").strip()))


def _invalid_result(
    *,
    raw: RawEvidenceIdentifier,
    outcome: EvidenceResolutionOutcome,
    warning: str,
    resolved_manifest_entry_id: str | None = None,
    role: ExecutionImageRole | None = None,
) -> EvidenceResolutionResult:
    return EvidenceResolutionResult(
        outcome=outcome,
        traceability_status=TraceabilityStatus.INVALID.value,
        raw_manifest_entry_id=raw.manifest_entry_id,
        raw_source_image_id=raw.legacy_source_image_id,
        resolved_manifest_entry_id=resolved_manifest_entry_id,
        resolved_source_image_id=None,
        role=role,
        traceability_warning=warning,
    )


def _manifest_entry_for_source(
    manifest: ExecutionImageManifest,
    source_image_id: str,
) -> ExecutionImageEntry | None:
    key = source_image_id.strip()
    for entry in manifest.ordered_entries():
        if entry.source_image_id == key:
            return entry
    return None


def _resolved_primary_from_manifest_entry(
    manifest: ExecutionImageManifest,
    manifest_entry_id: str,
) -> EvidenceResolutionResult | None:
    entry = manifest.entry_by_manifest_id().get(manifest_entry_id.strip())
    if entry is None:
        return None
    if entry.role == ExecutionImageRole.REFERENCE_IMAGE:
        return None
    return EvidenceResolutionResult(
        outcome=EvidenceResolutionOutcome.RESOLVED,
        traceability_status=None,
        resolved_manifest_entry_id=entry.manifest_entry_id,
        resolved_source_image_id=entry.source_image_id,
        role=entry.role,
    )


def raw_evidence_from_entity_dict(entity_dict: dict[str, Any]) -> RawEvidenceIdentifier:
    mid = entity_dict.get(EVIDENCE_RETURN_IDENTIFIER_FIELD)
    sid = entity_dict.get(LEGACY_EVIDENCE_RETURN_FIELD)
    return RawEvidenceIdentifier(
        manifest_entry_id=str(mid).strip() if mid is not None and str(mid).strip() else None,
        legacy_source_image_id=str(sid).strip() if sid is not None and str(sid).strip() else None,
    )


def raw_evidence_from_entity(entity: Entity) -> RawEvidenceIdentifier:
    raw_legacy = getattr(entity, "raw_source_image_id", None)
    return RawEvidenceIdentifier(
        manifest_entry_id=(
            str(entity.manifest_entry_id).strip()
            if getattr(entity, "manifest_entry_id", None)
            else None
        ),
        legacy_source_image_id=str(raw_legacy).strip() if raw_legacy else None,
    )


def resolve_raw_evidence_identifier(
    raw: RawEvidenceIdentifier,
    manifest: ExecutionImageManifest | None,
    *,
    manifest_required: bool = True,
) -> EvidenceResolutionResult:
    """Resolve provider evidence identifiers against the canonical execution manifest."""
    base = EvidenceResolutionResult(
        outcome=EvidenceResolutionOutcome.MISSING,
        traceability_status=TraceabilityStatus.MISSING.value,
        raw_manifest_entry_id=raw.manifest_entry_id,
        raw_source_image_id=raw.legacy_source_image_id,
        traceability_warning=WARNING_MISSING_EVIDENCE_ID,
    )

    mid = raw.manifest_entry_id
    legacy = raw.legacy_source_image_id

    if not mid and not legacy:
        return base

    if manifest is None:
        if manifest_required:
            return EvidenceResolutionResult(
                outcome=EvidenceResolutionOutcome.MANIFEST_UNAVAILABLE,
                traceability_status=TraceabilityStatus.UNVALIDATED.value,
                raw_manifest_entry_id=mid,
                raw_source_image_id=legacy,
                traceability_warning=WARNING_MANIFEST_UNAVAILABLE,
            )
        return EvidenceResolutionResult(
            outcome=EvidenceResolutionOutcome.LEGACY_DEFERRED,
            traceability_status=None,
            raw_manifest_entry_id=mid,
            raw_source_image_id=legacy,
        )

    if mid and is_malformed_manifest_entry_id(mid):
        return _invalid_result(
            raw=raw,
            outcome=EvidenceResolutionOutcome.INVALID_MALFORMED,
            warning=WARNING_MALFORMED_MANIFEST_ENTRY_ID,
        )

    mid_key = mid.strip() if mid else None
    legacy_key = legacy.strip() if legacy else None

    mid_resolved: EvidenceResolutionResult | None = None
    if mid_key:
        if _is_reference_manifest_entry_id(mid_key):
            return _invalid_result(
                raw=raw,
                outcome=EvidenceResolutionOutcome.INVALID_REFERENCE,
                warning=WARNING_REFERENCE_AS_EVIDENCE,
                resolved_manifest_entry_id=mid_key,
                role=ExecutionImageRole.REFERENCE_IMAGE,
            )
        if _is_primary_manifest_entry_id(mid_key):
            entry = manifest.entry_by_manifest_id().get(mid_key)
            if entry is None:
                return _invalid_result(
                    raw=raw,
                    outcome=EvidenceResolutionOutcome.INVALID_UNKNOWN,
                    warning=WARNING_UNKNOWN_MANIFEST_ENTRY_ID,
                )
            mid_resolved = _resolved_primary_from_manifest_entry(manifest, mid_key)
            if mid_resolved is None:
                return _invalid_result(
                    raw=raw,
                    outcome=EvidenceResolutionOutcome.INVALID_REFERENCE,
                    warning=WARNING_REFERENCE_AS_EVIDENCE,
                    resolved_manifest_entry_id=mid_key,
                    role=ExecutionImageRole.REFERENCE_IMAGE,
                )

    legacy_entry = _manifest_entry_for_source(manifest, legacy_key) if legacy_key else None
    legacy_resolved_sid = legacy_entry.source_image_id if legacy_entry else None
    legacy_resolved_mid = legacy_entry.manifest_entry_id if legacy_entry else None
    legacy_role = legacy_entry.role if legacy_entry else None

    if mid_key and legacy_key:
        if mid_resolved is None and mid_key:
            if _is_reference_manifest_entry_id(mid_key):
                return _invalid_result(
                    raw=raw,
                    outcome=EvidenceResolutionOutcome.INVALID_REFERENCE,
                    warning=WARNING_REFERENCE_AS_EVIDENCE,
                    resolved_manifest_entry_id=mid_key,
                    role=ExecutionImageRole.REFERENCE_IMAGE,
                )
            if _is_primary_manifest_entry_id(mid_key):
                return _invalid_result(
                    raw=raw,
                    outcome=EvidenceResolutionOutcome.INVALID_UNKNOWN,
                    warning=WARNING_UNKNOWN_MANIFEST_ENTRY_ID,
                )
        if legacy_entry is None:
            if mid_resolved:
                return _invalid_result(
                    raw=raw,
                    outcome=EvidenceResolutionOutcome.CONFLICT,
                    warning=WARNING_UNKNOWN_LEGACY_SOURCE,
                    resolved_manifest_entry_id=mid_resolved.resolved_manifest_entry_id,
                )
            return _invalid_result(
                raw=raw,
                outcome=EvidenceResolutionOutcome.INVALID_UNKNOWN,
                warning=WARNING_UNKNOWN_SOURCE_IMAGE_ID,
            )
        if mid_resolved and legacy_resolved_sid and mid_resolved.resolved_source_image_id != legacy_resolved_sid:
            return _invalid_result(
                raw=raw,
                outcome=EvidenceResolutionOutcome.CONFLICT,
                warning=WARNING_CONFLICTING_EVIDENCE_IDS,
                resolved_manifest_entry_id=mid_resolved.resolved_manifest_entry_id,
            )
        if mid_resolved:
            return EvidenceResolutionResult(
                outcome=EvidenceResolutionOutcome.RESOLVED,
                traceability_status=None,
                raw_manifest_entry_id=mid,
                raw_source_image_id=legacy,
                resolved_manifest_entry_id=mid_resolved.resolved_manifest_entry_id,
                resolved_source_image_id=mid_resolved.resolved_source_image_id,
                role=mid_resolved.role,
            )
        if legacy_entry.role == ExecutionImageRole.REFERENCE_IMAGE:
            return _invalid_result(
                raw=raw,
                outcome=EvidenceResolutionOutcome.INVALID_REFERENCE,
                warning=WARNING_REFERENCE_AS_EVIDENCE,
                resolved_manifest_entry_id=legacy_resolved_mid,
                role=ExecutionImageRole.REFERENCE_IMAGE,
            )
        return EvidenceResolutionResult(
            outcome=EvidenceResolutionOutcome.RESOLVED,
            traceability_status=None,
            raw_manifest_entry_id=mid,
            raw_source_image_id=legacy,
            resolved_manifest_entry_id=legacy_resolved_mid,
            resolved_source_image_id=legacy_resolved_sid,
            role=legacy_role,
        )

    if legacy_key and legacy_entry is None:
        return _invalid_result(
            raw=raw,
            outcome=EvidenceResolutionOutcome.INVALID_UNKNOWN,
            warning=WARNING_UNKNOWN_SOURCE_IMAGE_ID,
        )

    if legacy_entry and legacy_entry.role == ExecutionImageRole.REFERENCE_IMAGE:
        return _invalid_result(
            raw=raw,
            outcome=EvidenceResolutionOutcome.INVALID_REFERENCE,
            warning=WARNING_REFERENCE_SOURCE_ID,
            resolved_manifest_entry_id=legacy_resolved_mid,
            role=ExecutionImageRole.REFERENCE_IMAGE,
        )

    if mid_resolved:
        return EvidenceResolutionResult(
            outcome=EvidenceResolutionOutcome.RESOLVED,
            traceability_status=None,
            raw_manifest_entry_id=mid,
            raw_source_image_id=legacy,
            resolved_manifest_entry_id=mid_resolved.resolved_manifest_entry_id,
            resolved_source_image_id=mid_resolved.resolved_source_image_id,
            role=mid_resolved.role,
        )

    if legacy_entry:
        return EvidenceResolutionResult(
            outcome=EvidenceResolutionOutcome.RESOLVED,
            traceability_status=None,
            raw_manifest_entry_id=mid,
            raw_source_image_id=legacy,
            resolved_manifest_entry_id=legacy_resolved_mid,
            resolved_source_image_id=legacy_resolved_sid,
            role=legacy_role,
        )

    return _invalid_result(
        raw=raw,
        outcome=EvidenceResolutionOutcome.INVALID_UNKNOWN,
        warning=WARNING_UNKNOWN_MANIFEST_ENTRY_ID if mid_key else WARNING_UNKNOWN_SOURCE_IMAGE_ID,
    )


def _apply_resolution_to_entity(ent: Entity, result: EvidenceResolutionResult) -> None:
    if result.raw_manifest_entry_id is not None:
        ent.manifest_entry_id = result.raw_manifest_entry_id
    if result.raw_source_image_id is not None:
        ent.raw_source_image_id = result.raw_source_image_id
    ent.resolved_manifest_entry_id = result.resolved_manifest_entry_id

    if result.outcome == EvidenceResolutionOutcome.RESOLVED:
        ent.source_image_id = result.resolved_source_image_id
    else:
        ent.source_image_id = None

    if result.traceability_status:
        ent.traceability_status = result.traceability_status
    if result.traceability_warning:
        ent.traceability_warning = result.traceability_warning


def apply_evidence_resolution_to_entities(
    entities: list[Entity],
    *,
    composition: dict[str, Any] | None,
    manifest_required: bool | None = None,
) -> None:
    """Resolve raw evidence fields to canonical source_image_id or pre-mark invalid outcomes."""
    composition_has_key = composition_has_execution_image_manifest(composition)
    if manifest_required is None:
        require_manifest = composition_has_key
    else:
        require_manifest = manifest_required

    manifest: ExecutionImageManifest | None = None
    manifest_invalid = False

    if composition_has_key:
        try:
            manifest = require_manifest_from_composition(composition)
        except ExecutionImageManifestError:
            manifest_invalid = True
        if manifest is None and not manifest_invalid:
            manifest_invalid = True

    for ent in entities:
        raw = raw_evidence_from_entity(ent)
        if manifest_invalid:
            result = EvidenceResolutionResult(
                outcome=EvidenceResolutionOutcome.MANIFEST_INVALID,
                traceability_status=TraceabilityStatus.UNVALIDATED.value,
                raw_manifest_entry_id=raw.manifest_entry_id,
                raw_source_image_id=raw.legacy_source_image_id,
                traceability_warning=WARNING_MANIFEST_INVALID,
            )
        else:
            result = resolve_raw_evidence_identifier(
                raw,
                manifest,
                manifest_required=require_manifest,
            )
        _apply_resolution_to_entity(ent, result)


def merge_evidence_resolution_results(
    left: EvidenceResolutionResult,
    right: EvidenceResolutionResult,
) -> EvidenceResolutionResult:
    """Deterministic merge policy for duplicate entity evidence (Phase 4.5)."""

    def _rank(result: EvidenceResolutionResult) -> int:
        status = result.traceability_status
        if status == TraceabilityStatus.VALID.value:
            return 4
        if result.outcome == EvidenceResolutionOutcome.RESOLVED:
            return 3
        if status == TraceabilityStatus.INVALID.value:
            return 2
        if status == TraceabilityStatus.MISSING.value:
            return 1
        return 0

    left_rank = _rank(left)
    right_rank = _rank(right)
    if left_rank > right_rank:
        winner, loser = left, right
    elif right_rank > left_rank:
        winner, loser = right, left
    else:
        winner, loser = (left, right) if (left.resolved_source_image_id or "") <= (
            right.resolved_source_image_id or ""
        ) else (right, left)

    warning = winner.traceability_warning
    if (
        left.outcome == EvidenceResolutionOutcome.RESOLVED
        and right.outcome == EvidenceResolutionOutcome.RESOLVED
        and left.resolved_source_image_id
        and right.resolved_source_image_id
        and left.resolved_source_image_id != right.resolved_source_image_id
    ):
        warning = WARNING_MERGE_MULTIPLE_VALID_SOURCES
    elif left.outcome == EvidenceResolutionOutcome.CONFLICT or right.outcome == EvidenceResolutionOutcome.CONFLICT:
        if winner.outcome == EvidenceResolutionOutcome.RESOLVED:
            warning = loser.traceability_warning or WARNING_MERGE_EVIDENCE_CONFLICT

    return EvidenceResolutionResult(
        outcome=winner.outcome,
        traceability_status=winner.traceability_status,
        raw_manifest_entry_id=winner.raw_manifest_entry_id or loser.raw_manifest_entry_id,
        raw_source_image_id=winner.raw_source_image_id or loser.raw_source_image_id,
        resolved_manifest_entry_id=winner.resolved_manifest_entry_id,
        resolved_source_image_id=winner.resolved_source_image_id,
        role=winner.role,
        traceability_warning=warning,
    )


def merge_entity_evidence_fields(target: Entity, candidate: Entity) -> None:
    """Apply merge policy when consolidating duplicate parsed entities."""
    from src.domain.traceability import normalize_traceability_status

    def _priority(ent: Entity) -> int:
        status = normalize_traceability_status(ent.traceability_status)
        if status == TraceabilityStatus.VALID.value:
            return 4
        if ent.source_image_id and status is None:
            return 3
        if status == TraceabilityStatus.INVALID.value:
            return 2
        if status == TraceabilityStatus.MISSING.value:
            return 1
        return 0

    if _priority(candidate) > _priority(target):
        winner, loser = candidate, target
    elif _priority(target) > _priority(candidate):
        winner, loser = target, candidate
    else:
        winner, loser = (
            (target, candidate)
            if (target.source_image_id or "") <= (candidate.source_image_id or "")
            else (candidate, target)
        )

    target.manifest_entry_id = winner.manifest_entry_id or loser.manifest_entry_id
    target.raw_source_image_id = winner.raw_source_image_id or loser.raw_source_image_id
    target.resolved_manifest_entry_id = winner.resolved_manifest_entry_id
    target.source_image_id = winner.source_image_id
    target.traceability_status = winner.traceability_status
    target.traceability_warning = winner.traceability_warning

    if (
        winner.source_image_id
        and loser.source_image_id
        and winner.source_image_id != loser.source_image_id
        and normalize_traceability_status(winner.traceability_status) == TraceabilityStatus.VALID.value
        and normalize_traceability_status(loser.traceability_status) == TraceabilityStatus.VALID.value
    ):
        target.traceability_warning = WARNING_MERGE_MULTIPLE_VALID_SOURCES


# Backward-compatible alias used by entity resolution stage.
normalize_entity_evidence_identifiers = apply_evidence_resolution_to_entities
