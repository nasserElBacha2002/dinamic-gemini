"""
Phase 4.4 — Structured projection of image IDs emitted by prompt composition.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from src.domain.execution_image_manifest import (
    MANIFEST_VERSION,
    ExecutionImageManifest,
    ExecutionImageRole,
)

COMPOSITION_KEY_PROMPT_IMAGE_PROJECTION = "prompt_image_projection"


@dataclass(frozen=True)
class PromptImageProjection:
    """Exact manifest entry IDs listed in the composed prompt (by section and order)."""

    ordered_manifest_entry_ids: tuple[str, ...]
    primary_manifest_entry_ids: tuple[str, ...]
    reference_manifest_entry_ids: tuple[str, ...]
    manifest_version: int = MANIFEST_VERSION
    prompt_image_section_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordered_manifest_entry_ids": list(self.ordered_manifest_entry_ids),
            "primary_manifest_entry_ids": list(self.primary_manifest_entry_ids),
            "reference_manifest_entry_ids": list(self.reference_manifest_entry_ids),
            "manifest_version": self.manifest_version,
            "prompt_image_section_hash": self.prompt_image_section_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PromptImageProjection:
        return cls(
            ordered_manifest_entry_ids=tuple(
                str(x).strip() for x in raw.get("ordered_manifest_entry_ids") or [] if str(x).strip()
            ),
            primary_manifest_entry_ids=tuple(
                str(x).strip() for x in raw.get("primary_manifest_entry_ids") or [] if str(x).strip()
            ),
            reference_manifest_entry_ids=tuple(
                str(x).strip()
                for x in raw.get("reference_manifest_entry_ids") or []
                if str(x).strip()
            ),
            manifest_version=int(raw.get("manifest_version") or MANIFEST_VERSION),
            prompt_image_section_hash=(
                str(raw["prompt_image_section_hash"]).strip()
                if raw.get("prompt_image_section_hash")
                else None
            ),
        )


def build_prompt_image_projection_from_manifest(
    manifest: ExecutionImageManifest,
    *,
    image_section_text: str | None = None,
) -> PromptImageProjection:
    """Build projection from manifest entries (same source as prompt image sections)."""
    ordered = manifest.ordered_entries()
    primary = tuple(e.manifest_entry_id for e in ordered if e.role == ExecutionImageRole.PRIMARY_EVIDENCE)
    reference = tuple(e.manifest_entry_id for e in ordered if e.role == ExecutionImageRole.REFERENCE_IMAGE)
    section_hash = None
    if image_section_text:
        section_hash = hashlib.sha256(image_section_text.encode("utf-8")).hexdigest()
    return PromptImageProjection(
        ordered_manifest_entry_ids=tuple(e.manifest_entry_id for e in ordered),
        primary_manifest_entry_ids=primary,
        reference_manifest_entry_ids=reference,
        manifest_version=manifest.version,
        prompt_image_section_hash=section_hash,
    )


def prompt_projection_from_composition(composition: dict[str, Any] | None) -> PromptImageProjection | None:
    if not composition:
        return None
    raw = composition.get(COMPOSITION_KEY_PROMPT_IMAGE_PROJECTION)
    if isinstance(raw, PromptImageProjection):
        return raw
    if isinstance(raw, dict):
        return PromptImageProjection.from_dict(raw)
    return None
