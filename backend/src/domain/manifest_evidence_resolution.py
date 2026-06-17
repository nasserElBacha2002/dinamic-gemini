"""
Phase 4.4 — Normalize model-returned evidence identifiers to stable source_image_id.
"""

from __future__ import annotations

from typing import Any

from src.domain.entity import Entity
from src.domain.execution_image_manifest import (
    ExecutionImageManifest,
    LEGACY_EVIDENCE_RETURN_FIELD,
    require_manifest_from_composition,
)


def normalize_entity_evidence_identifiers(
    entities: list[Entity],
    *,
    composition: dict[str, Any] | None,
) -> None:
    """
  Resolve ``manifest_entry_id`` (preferred) or legacy ``source_image_id`` from model output
    to stable ``source_image_id`` on each entity before traceability validation.
    """
    manifest = require_manifest_from_composition(composition)
    if manifest is None:
        return
    entry_by_mid = manifest.entry_by_manifest_id()
    for ent in entities:
        raw_sid = ent.source_image_id
        evidence_raw = (raw_sid or "").strip()
        if not evidence_raw:
            continue
        if evidence_raw in entry_by_mid:
            ent.source_image_id = entry_by_mid[evidence_raw].source_image_id
            continue
        resolved = manifest.resolve_source_image_id(evidence_raw)
        if resolved:
            ent.source_image_id = resolved
            continue
        # Legacy: model may still return source_image_id UUID directly.
        if raw_sid and manifest.resolve_source_image_id(raw_sid):
            ent.source_image_id = manifest.resolve_source_image_id(raw_sid)


def extract_raw_evidence_id_from_entity_dict(entity_dict: dict[str, Any]) -> str | None:
    """Read preferred manifest_entry_id then legacy source_image_id from raw entity JSON."""
    mid = entity_dict.get("manifest_entry_id")
    if mid is not None and str(mid).strip():
        return str(mid).strip()
    sid = entity_dict.get(LEGACY_EVIDENCE_RETURN_FIELD)
    if sid is not None and str(sid).strip():
        return str(sid).strip()
    return None
