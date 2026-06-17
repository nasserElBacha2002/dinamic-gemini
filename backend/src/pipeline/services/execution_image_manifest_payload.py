"""
Phase 4.3 corrections — bind provider request image inputs from ExecutionImageManifest.

The manifest is the sole authority for which images are sent and in what order.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.domain.execution_image_manifest import (
    ExecutionImageManifest,
    ExecutionImageManifestError,
    ExecutionImageRole,
)


@dataclass(frozen=True)
class ManifestBoundProviderPayload:
    """Provider-bound image inputs derived exclusively from a validated manifest."""

    frame_paths: tuple[Path, ...]
    frames_nd: tuple[Any, ...]
    frame_refs: tuple[str, ...]
    context_images: tuple[Any, ...]
    reference_image_ids: tuple[str, ...]

    @property
    def primary_count(self) -> int:
        return len(self.frame_refs)

    @property
    def reference_count(self) -> int:
        return len(self.reference_image_ids)


def bind_provider_payload_from_manifest(
    manifest: ExecutionImageManifest,
    *,
    primary_path_by_source_id: Mapping[str, Path],
    primary_nd_by_source_id: Mapping[str, Any],
    reference_image_by_source_id: Mapping[str, Any],
) -> ManifestBoundProviderPayload:
    """
    Materialize provider payload collections from manifest entries (references first, then primaries).

    Raises ``ExecutionImageManifestError`` when any active manifest entry lacks bound image data.
    """
    reference_ids: list[str] = []
    context_images: list[Any] = []
    for entry in manifest.reference_entries():
        image = reference_image_by_source_id.get(entry.source_image_id)
        if image is None:
            raise ExecutionImageManifestError(
                f"reference image not bound for manifest entry {entry.manifest_entry_id} "
                f"(source_image_id={entry.source_image_id!r})"
            )
        reference_ids.append(entry.source_image_id)
        context_images.append(image)

    frame_paths: list[Path] = []
    frames_nd: list[Any] = []
    frame_refs: list[str] = []
    for entry in manifest.primary_entries():
        sid = entry.source_image_id
        path = primary_path_by_source_id.get(sid)
        nd = primary_nd_by_source_id.get(sid)
        if path is None or nd is None:
            raise ExecutionImageManifestError(
                f"primary image not bound for manifest entry {entry.manifest_entry_id} "
                f"(source_image_id={sid!r})"
            )
        frame_paths.append(path)
        frames_nd.append(nd)
        frame_refs.append(sid)

    payload = ManifestBoundProviderPayload(
        frame_paths=tuple(frame_paths),
        frames_nd=tuple(frames_nd),
        frame_refs=tuple(frame_refs),
        context_images=tuple(context_images),
        reference_image_ids=tuple(reference_ids),
    )
    assert_provider_payload_matches_manifest(manifest, payload)
    return payload


def assert_provider_payload_matches_manifest(
    manifest: ExecutionImageManifest,
    payload: ManifestBoundProviderPayload,
) -> None:
    """Adapter-boundary check: payload order and IDs must match manifest authority."""
    expected_primary = list(manifest.primary_source_image_ids())
    expected_refs = list(manifest.reference_source_image_ids())
    actual_primary = list(payload.frame_refs)
    actual_refs = list(payload.reference_image_ids)
    if actual_primary != expected_primary:
        raise ExecutionImageManifestError(
            f"provider primary order mismatch: manifest={expected_primary!r} payload={actual_primary!r}"
        )
    if actual_refs != expected_refs:
        raise ExecutionImageManifestError(
            f"provider reference order mismatch: manifest={expected_refs!r} payload={actual_refs!r}"
        )
    if len(payload.context_images) != len(expected_refs):
        raise ExecutionImageManifestError(
            f"reference image count mismatch: manifest={len(expected_refs)} payload={len(payload.context_images)}"
        )
    if len(payload.frames_nd) != len(expected_primary):
        raise ExecutionImageManifestError(
            f"primary image count mismatch: manifest={len(expected_primary)} payload={len(payload.frames_nd)}"
        )


def primary_lookups_from_acquired(
    frame_paths: list[Path],
    frame_refs: list[str],
    frames_nd: list[Any],
) -> tuple[dict[str, Path], dict[str, Any]]:
    """Build source_image_id lookups from positionally aligned acquisition output."""
    if len(frame_paths) != len(frame_refs) or len(frames_nd) != len(frame_refs):
        raise ExecutionImageManifestError(
            f"acquired frame collections misaligned: paths={len(frame_paths)} "
            f"refs={len(frame_refs)} nd={len(frames_nd)}"
        )
    path_by: dict[str, Path] = {}
    nd_by: dict[str, Any] = {}
    for i, sid in enumerate(frame_refs):
        key = (sid or "").strip()
        if not key:
            continue
        path_by[key] = frame_paths[i]
        nd_by[key] = frames_nd[i]
    return path_by, nd_by


def reference_lookup_from_visual_bundle(
    context_images: list[Any] | None,
    resolved_reference_ids: list[str],
) -> dict[str, Any]:
    """Map reference source_image_id → loaded image (parallel lists from visual bundle)."""
    images = list(context_images or [])
    if len(images) != len(resolved_reference_ids):
        raise ExecutionImageManifestError(
            f"reference bundle misaligned: images={len(images)} ids={len(resolved_reference_ids)}"
        )
    return {
        (rid or "").strip(): images[i]
        for i, rid in enumerate(resolved_reference_ids)
        if (rid or "").strip()
    }


def validate_provider_lists_against_manifest(
    manifest: ExecutionImageManifest,
    *,
    frame_refs: list[str],
    reference_image_ids: list[str],
) -> None:
    """Adapter entry check: legacy list parameters must match manifest authority."""
    if list(manifest.primary_source_image_ids()) != list(frame_refs):
        raise ExecutionImageManifestError(
            f"adapter frame_refs mismatch manifest primaries: "
            f"manifest={list(manifest.primary_source_image_ids())!r} adapter={frame_refs!r}"
        )
    if list(manifest.reference_source_image_ids()) != list(reference_image_ids):
        raise ExecutionImageManifestError(
            f"adapter reference_image_ids mismatch manifest: "
            f"manifest={list(manifest.reference_source_image_ids())!r} adapter={reference_image_ids!r}"
        )


def manifest_from_request_metadata(metadata: dict[str, Any] | None) -> ExecutionImageManifest | None:
    """Load manifest from LLM request metadata prompt composition when present."""
    if not metadata:
        return None
    from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_COMPOSITION
    from src.domain.execution_image_manifest import (
        composition_has_execution_image_manifest,
        require_manifest_from_composition,
    )

    comp = metadata.get(LLM_METADATA_KEY_PROMPT_COMPOSITION)
    if not isinstance(comp, dict) or not composition_has_execution_image_manifest(comp):
        return None
    return require_manifest_from_composition(comp)


def multimodal_source_ids_from_payload(
    payload: ManifestBoundProviderPayload,
) -> list[tuple[str, str, int]]:
    """
    Ordered multimodal image identities for diagnostics: (role, source_image_id, provider_position).

    References occupy positions 1..R; primaries R+1..R+P (image parts only, not prompt text).
    """
    rows: list[tuple[str, str, int]] = []
    pos = 1
    for sid in payload.reference_image_ids:
        rows.append((ExecutionImageRole.REFERENCE_IMAGE.value, sid, pos))
        pos += 1
    for sid in payload.frame_refs:
        rows.append((ExecutionImageRole.PRIMARY_EVIDENCE.value, sid, pos))
        pos += 1
    return rows
