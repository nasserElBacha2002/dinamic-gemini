"""
Phase 4.4 — Centralized provider-neutral multimodal serialization and parity validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domain.execution_image_manifest import ExecutionImageRole
from src.llm.vision_multimodal_payload import (
    ROLE_PRIMARY_EVIDENCE,
    ROLE_REFERENCE_ONLY,
)
from src.pipeline.services.provider_execution_errors import (
    PROVIDER_IMAGE_MANIFEST_MISMATCH,
    PROVIDER_IMAGE_RESOURCE_MISSING,
    PROVIDER_IMAGE_SERIALIZATION_FAILED,
    ProviderImageExecutionError,
)
from src.pipeline.services.provider_execution_request import (
    PROVIDER_IMAGE_MANIFEST_ORDER_KEY,
    ProviderExecutionImage,
    ProviderExecutionRequest,
)


@dataclass(frozen=True)
class SerializedImagePayloadEntry:
    """One image in the provider-neutral serialized projection."""

    manifest_entry_id: str
    source_image_id: str
    role: ExecutionImageRole
    payload_ordinal: int
    provider_image_position: int
    mime_type: str
    encoded_resource: object


@dataclass(frozen=True)
class SerializedMultimodalPayload:
    """Provider-neutral serialized image set derived from ProviderExecutionRequest."""

    entries: tuple[SerializedImagePayloadEntry, ...]
    provider_image_manifest_order: tuple[dict[str, Any], ...]
    logical_projection: tuple[tuple[str, str], ...]

    @property
    def image_count(self) -> int:
        return len(self.entries)


def _validate_runtime_resource(image: ProviderExecutionImage) -> None:
    resource = image.runtime_resource.resource
    if resource is None:
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_RESOURCE_MISSING,
            f"runtime resource missing for {image.manifest_entry_id}",
            manifest_entry_id=image.manifest_entry_id,
            role=image.role.value,
        )
    if image.runtime_resource.is_primary_ndarray:
        try:
            import numpy as np

            arr = np.asarray(resource)
            if arr.size == 0:
                raise ProviderImageExecutionError(
                    PROVIDER_IMAGE_SERIALIZATION_FAILED,
                    f"empty primary ndarray for {image.manifest_entry_id}",
                    manifest_entry_id=image.manifest_entry_id,
                    role=image.role.value,
                )
        except ProviderImageExecutionError:
            raise
        except Exception as exc:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_SERIALIZATION_FAILED,
                f"invalid primary ndarray for {image.manifest_entry_id}",
                manifest_entry_id=image.manifest_entry_id,
                role=image.role.value,
            ) from exc


def serialize_provider_images(
    request: ProviderExecutionRequest,
    *,
    job_id: str | None = None,
    provider: str | None = None,
) -> SerializedMultimodalPayload:
    """
    Serialize manifest-ordered images without reordering, filtering, or role inference.

    ``encoded_resource`` retains the runtime object (ndarray / PIL) for adapter materialization.
    """
    entries: list[SerializedImagePayloadEntry] = []
    order_meta: list[dict[str, Any]] = []
    logical: list[tuple[str, str]] = []
    provider_pos = 0

    for image in request.ordered_images():
        _validate_runtime_resource(image)
        entries.append(
            SerializedImagePayloadEntry(
                manifest_entry_id=image.manifest_entry_id,
                source_image_id=image.source_image_id,
                role=image.role,
                payload_ordinal=image.payload_ordinal,
                provider_image_position=provider_pos,
                mime_type=image.mime_type or "image/jpeg",
                encoded_resource=image.runtime_resource.resource,
            )
        )
        order_meta.append(
            {
                "provider_position": provider_pos,
                "manifest_entry_id": image.manifest_entry_id,
                "source_image_id": image.source_image_id,
                "role": image.role.value,
                "payload_ordinal": image.payload_ordinal,
            }
        )
        logical.append((image.manifest_entry_id, image.role.value))
        provider_pos += 1

    payload = SerializedMultimodalPayload(
        entries=tuple(entries),
        provider_image_manifest_order=tuple(order_meta),
        logical_projection=tuple(logical),
    )
    validate_prompt_payload_manifest_parity(
        request.image_manifest,
        prompt_projection=_prompt_image_projection_from_manifest(request),
        serialized_payload_projection=payload,
        job_id=job_id or request.job_id,
        provider=provider,
    )
    return payload


def _prompt_image_projection_from_manifest(
    request: ProviderExecutionRequest,
) -> list[tuple[str, str, int]]:
    """Manifest entry IDs listed in prompt order (payload_ordinal ascending)."""
    return [
        (img.manifest_entry_id, img.role.value, img.payload_ordinal)
        for img in request.ordered_images()
    ]


def validate_prompt_payload_manifest_parity(
    manifest: Any,
    *,
    prompt_projection: list[tuple[str, str, int]],
    serialized_payload_projection: SerializedMultimodalPayload,
    job_id: str | None = None,
    provider: str | None = None,
) -> None:
    """Detect prompt/payload/manifest identity or order mismatches before remote execution."""
    manifest_ordered = manifest.ordered_entries()
    prompt_ids = [row[0] for row in prompt_projection]
    payload_ids = [e.manifest_entry_id for e in serialized_payload_projection.entries]
    manifest_ids = [e.manifest_entry_id for e in manifest_ordered]

    if prompt_ids != manifest_ids:
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_MANIFEST_MISMATCH,
            f"prompt/manifest entry order mismatch: prompt={prompt_ids!r} manifest={manifest_ids!r}",
            job_id=job_id,
            provider=provider,
        )
    if payload_ids != manifest_ids:
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_MANIFEST_MISMATCH,
            f"payload/manifest entry order mismatch: payload={payload_ids!r} manifest={manifest_ids!r}",
            job_id=job_id,
            provider=provider,
        )
    if len(prompt_ids) != len(set(prompt_ids)):
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_MANIFEST_MISMATCH,
            "duplicate manifest_entry_id in prompt projection",
            job_id=job_id,
            provider=provider,
        )

    for i, entry in enumerate(serialized_payload_projection.entries):
        manifest_entry = manifest_ordered[i]
        if entry.role != manifest_entry.role:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"role mismatch for {entry.manifest_entry_id}",
                job_id=job_id,
                provider=provider,
                manifest_entry_id=entry.manifest_entry_id,
                role=entry.role.value,
            )
        if entry.source_image_id != manifest_entry.source_image_id:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"source_image_id mismatch for {entry.manifest_entry_id}",
                job_id=job_id,
                provider=provider,
                manifest_entry_id=entry.manifest_entry_id,
            )
        if entry.provider_image_position != i:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"provider position mismatch for {entry.manifest_entry_id}",
                job_id=job_id,
                provider=provider,
                manifest_entry_id=entry.manifest_entry_id,
            )

    for row in prompt_projection:
        mid, role, ordinal = row
        if ordinal < 1 or ordinal > len(manifest_ordered):
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"invalid prompt ordinal for {mid}",
                job_id=job_id,
                provider=provider,
                manifest_entry_id=mid,
            )


def manifest_entry_label(image: SerializedImagePayloadEntry) -> str:
    """Text label immediately preceding a vision part in provider payloads."""
    if image.role == ExecutionImageRole.REFERENCE_IMAGE:
        return (
            "Reference image\n"
            f"manifest_entry_id: {image.manifest_entry_id}\n"
            f"source_image_id: {image.source_image_id}\n"
            f"role: {ROLE_REFERENCE_ONLY}\n"
            "Do not use this image as evidence."
        )
    return (
        "Primary evidence image\n"
        f"manifest_entry_id: {image.manifest_entry_id}\n"
        f"source_image_id: {image.source_image_id}\n"
        f"role: {ROLE_PRIMARY_EVIDENCE}\n"
        f"provider_image_position: {image.provider_image_position}"
    )


def record_provider_image_manifest_order(
    metadata: dict[str, Any],
    serialized: SerializedMultimodalPayload,
) -> None:
    """Persist auditable mapping derived from actual serialized payload."""
    metadata[PROVIDER_IMAGE_MANIFEST_ORDER_KEY] = list(
        serialized.provider_image_manifest_order
    )


def logical_projection_from_serialized(
    serialized: SerializedMultimodalPayload,
) -> list[list[str]]:
    """Cross-provider comparable logical projection: [[manifest_entry_id, role], ...]."""
    return [[mid, role] for mid, role in serialized.logical_projection]
