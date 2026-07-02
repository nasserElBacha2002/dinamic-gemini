"""Resolve primary execution-image manifest entry for job-level review context."""

from __future__ import annotations

from typing import Any

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageManifestError,
    composition_has_execution_image_manifest,
    require_manifest_from_composition,
)


def load_execution_image_manifest(
    prompt_composition: dict[str, Any] | None,
) -> ExecutionImageManifest | None:
    if not composition_has_execution_image_manifest(prompt_composition):
        return None
    try:
        return require_manifest_from_composition(prompt_composition)
    except ExecutionImageManifestError:
        return None


def primary_manifest_entry(
    prompt_composition: dict[str, Any] | None,
) -> ExecutionImageEntry | None:
    manifest = load_execution_image_manifest(prompt_composition)
    if manifest is None:
        return None
    primaries = manifest.primary_entries()
    if not primaries:
        return None
    return primaries[0]
