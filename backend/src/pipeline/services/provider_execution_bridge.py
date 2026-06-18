"""
Phase 4.4 — Bridge ProviderExecutionRequest to legacy LLMRequest list parameters.

Centralized compatibility projection only; no independent image-selection decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.execution_image_manifest import ExecutionImageRole
from src.pipeline.services.provider_execution_request import ProviderExecutionRequest


@dataclass(frozen=True)
class LegacyProviderLists:
    """Derived legacy adapter lists — not authoritative when manifest contract is present."""

    frame_paths: tuple[Path, ...]
    frames_nd: tuple[Any, ...]
    frame_refs: tuple[str, ...]
    context_images: tuple[Any, ...]
    reference_image_ids: tuple[str, ...]


def legacy_lists_from_provider_request(
    request: ProviderExecutionRequest,
) -> LegacyProviderLists:
    """
    Deterministic legacy list projection from canonical provider request.

    Order follows ``payload_ordinal`` (references first, then primaries per manifest).
    """
    frame_paths: list[Path] = []
    frames_nd: list[Any] = []
    frame_refs: list[str] = []
    context_images: list[Any] = []
    reference_image_ids: list[str] = []

    for image in request.ordered_images():
        if image.role == ExecutionImageRole.REFERENCE_IMAGE:
            context_images.append(image.runtime_resource.resource)
            reference_image_ids.append(image.source_image_id)
        else:
            frames_nd.append(image.runtime_resource.resource)
            frame_refs.append(image.source_image_id)
            if image.runtime_resource.storage_path is not None:
                frame_paths.append(image.runtime_resource.storage_path)

    return LegacyProviderLists(
        frame_paths=tuple(frame_paths),
        frames_nd=tuple(frames_nd),
        frame_refs=tuple(frame_refs),
        context_images=tuple(context_images),
        reference_image_ids=tuple(reference_image_ids),
    )
