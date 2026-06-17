"""
Phase 4.4 — Provider-neutral execution request bound to ExecutionImageManifest.

Single authoritative input contract for all active visual provider adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.domain.execution_image_manifest import (
    ExecutionImageManifest,
    ExecutionImageManifestError,
    ExecutionImageRole,
    validate_execution_image_manifest,
)
from src.pipeline.services.execution_image_manifest_payload import ManifestBoundProviderPayload
from src.pipeline.services.provider_execution_errors import (
    PROVIDER_IMAGE_MANIFEST_MISMATCH,
    PROVIDER_IMAGE_RESOURCE_MISSING,
    ProviderImageExecutionError,
)

PROVIDER_EXECUTION_REQUEST_METADATA_KEY = "provider_execution_request"
PROVIDER_IMAGE_MANIFEST_ORDER_KEY = "provider_image_manifest_order"

SUPPORTED_IMAGE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
)


@dataclass(frozen=True)
class ImageRuntimeResource:
    """Provider-neutral runtime image resource (no SDK types)."""

    resource: Any
    storage_path: Path | None = None
    mime_type: str | None = None
    is_primary_ndarray: bool = False


@dataclass(frozen=True)
class ProviderExecutionImage:
    """One manifest-aligned image ready for provider serialization."""

    manifest_entry_id: str
    source_image_id: str
    source_asset_id: str
    role: ExecutionImageRole
    payload_ordinal: int
    runtime_resource: ImageRuntimeResource
    mime_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_entry_id": self.manifest_entry_id,
            "source_image_id": self.source_image_id,
            "source_asset_id": self.source_asset_id,
            "role": self.role.value,
            "payload_ordinal": self.payload_ordinal,
            "mime_type": self.mime_type,
            "has_runtime_resource": self.runtime_resource.resource is not None,
            "is_primary_ndarray": self.runtime_resource.is_primary_ndarray,
        }


@dataclass(frozen=True)
class ProviderExecutionRequest:
    """Immutable provider-neutral request for one visual LLM execution."""

    job_id: str
    prompt: str
    image_manifest: ExecutionImageManifest
    images: tuple[ProviderExecutionImage, ...]
    schema_version: str
    metadata: Mapping[str, Any]

    def ordered_images(self) -> tuple[ProviderExecutionImage, ...]:
        return tuple(sorted(self.images, key=lambda i: i.payload_ordinal))

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "schema_version": self.schema_version,
            "image_manifest": self.image_manifest.to_dict(),
            "images": [img.to_dict() for img in self.ordered_images()],
        }


def infer_mime_type(
    *,
    declared_mime: str | None,
    storage_path: Path | None,
    original_filename: str | None = None,
) -> str:
    """Central MIME inference — filename used only when no declared MIME."""
    if declared_mime and str(declared_mime).strip():
        m = str(declared_mime).strip().lower()
        if m in SUPPORTED_IMAGE_MIME_TYPES:
            return m
    name = (original_filename or (str(storage_path) if storage_path else "")).lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def build_provider_execution_request(
    *,
    job_id: str,
    prompt: str,
    manifest: ExecutionImageManifest,
    bound_payload: ManifestBoundProviderPayload,
    schema_version: str = "v2.1",
    metadata: Mapping[str, Any] | None = None,
) -> ProviderExecutionRequest:
    """Materialize provider-neutral images from manifest + bound runtime resources."""
    validate_execution_image_manifest(manifest)

    ref_resources = list(bound_payload.context_images)
    ref_ids = list(bound_payload.reference_image_ids)
    primary_nd = list(bound_payload.frames_nd)
    primary_paths = list(bound_payload.frame_paths)
    primary_ids = list(bound_payload.frame_refs)

    if len(ref_resources) != len(ref_ids):
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_MANIFEST_MISMATCH,
            "reference runtime resources misaligned with manifest",
            job_id=job_id,
        )
    if len(primary_nd) != len(primary_ids) or len(primary_paths) != len(primary_ids):
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_MANIFEST_MISMATCH,
            "primary runtime resources misaligned with manifest",
            job_id=job_id,
        )

    ref_by_sid = {sid: ref_resources[i] for i, sid in enumerate(ref_ids)}
    nd_by_sid = {primary_ids[i]: primary_nd[i] for i in range(len(primary_ids))}
    path_by_sid = {primary_ids[i]: primary_paths[i] for i in range(len(primary_paths))}

    images: list[ProviderExecutionImage] = []
    for entry in manifest.ordered_entries():
        if entry.role == ExecutionImageRole.REFERENCE_IMAGE:
            resource_obj = ref_by_sid.get(entry.source_image_id)
            if resource_obj is None:
                raise ProviderImageExecutionError(
                    PROVIDER_IMAGE_RESOURCE_MISSING,
                    f"reference resource missing for {entry.manifest_entry_id}",
                    job_id=job_id,
                    manifest_entry_id=entry.manifest_entry_id,
                    role=entry.role.value,
                )
            runtime = ImageRuntimeResource(resource=resource_obj, is_primary_ndarray=False)
        else:
            nd = nd_by_sid.get(entry.source_image_id)
            path = path_by_sid.get(entry.source_image_id)
            if nd is None:
                raise ProviderImageExecutionError(
                    PROVIDER_IMAGE_RESOURCE_MISSING,
                    f"primary resource missing for {entry.manifest_entry_id}",
                    job_id=job_id,
                    manifest_entry_id=entry.manifest_entry_id,
                    role=entry.role.value,
                )
            runtime = ImageRuntimeResource(
                resource=nd,
                storage_path=path,
                is_primary_ndarray=True,
            )
        mime = infer_mime_type(
            declared_mime=entry.mime_type,
            storage_path=runtime.storage_path,
            original_filename=entry.original_filename,
        )
        if mime not in SUPPORTED_IMAGE_MIME_TYPES:
            raise ProviderImageExecutionError(
                "PROVIDER_IMAGE_UNSUPPORTED_FORMAT",
                f"unsupported MIME for {entry.manifest_entry_id}: {mime}",
                job_id=job_id,
                manifest_entry_id=entry.manifest_entry_id,
                role=entry.role.value,
            )
        images.append(
            ProviderExecutionImage(
                manifest_entry_id=entry.manifest_entry_id,
                source_image_id=entry.source_image_id,
                source_asset_id=entry.source_asset_id,
                role=entry.role,
                payload_ordinal=entry.payload_ordinal,
                runtime_resource=runtime,
                mime_type=mime,
            )
        )

    request = ProviderExecutionRequest(
        job_id=job_id,
        prompt=prompt,
        image_manifest=manifest,
        images=tuple(images),
        schema_version=schema_version,
        metadata=dict(metadata or {}),
    )
    validate_provider_execution_request(request)
    return request


def validate_provider_execution_request(request: ProviderExecutionRequest) -> None:
    """Invariant checks before adapter serialization."""
    manifest = request.image_manifest
    ordered = request.ordered_images()
    manifest_ordered = manifest.ordered_entries()

    if len(ordered) != len(manifest_ordered):
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_MANIFEST_MISMATCH,
            f"image count mismatch: manifest={len(manifest_ordered)} request={len(ordered)}",
            job_id=request.job_id,
        )

    seen_entry_ids: set[str] = set()
    seen_source_ids: set[str] = set()
    for i, (img, entry) in enumerate(zip(ordered, manifest_ordered)):
        expected_ordinal = i + 1
        if img.payload_ordinal != expected_ordinal or entry.payload_ordinal != expected_ordinal:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"payload_ordinal mismatch at position {expected_ordinal}",
                job_id=request.job_id,
            )
        if img.manifest_entry_id != entry.manifest_entry_id:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"manifest_entry_id mismatch at ordinal {expected_ordinal}",
                job_id=request.job_id,
                manifest_entry_id=img.manifest_entry_id,
            )
        if img.source_image_id != entry.source_image_id:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"source_image_id mismatch for {img.manifest_entry_id}",
                job_id=request.job_id,
                manifest_entry_id=img.manifest_entry_id,
            )
        if img.role != entry.role:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"role mismatch for {img.manifest_entry_id}",
                job_id=request.job_id,
                manifest_entry_id=img.manifest_entry_id,
                role=img.role.value,
            )
        if img.manifest_entry_id in seen_entry_ids:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"duplicate manifest_entry_id: {img.manifest_entry_id}",
                job_id=request.job_id,
            )
        if img.source_image_id in seen_source_ids:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_MANIFEST_MISMATCH,
                f"duplicate source_image_id: {img.source_image_id}",
                job_id=request.job_id,
            )
        seen_entry_ids.add(img.manifest_entry_id)
        seen_source_ids.add(img.source_image_id)
        if img.runtime_resource.resource is None:
            raise ProviderImageExecutionError(
                PROVIDER_IMAGE_RESOURCE_MISSING,
                f"runtime resource missing for {img.manifest_entry_id}",
                job_id=request.job_id,
                manifest_entry_id=img.manifest_entry_id,
                role=img.role.value,
            )


def provider_execution_request_from_metadata(
    metadata: dict[str, Any] | None,
) -> ProviderExecutionRequest | None:
    """Rehydrate request contract from LLM metadata when present."""
    if not metadata:
        return None
    raw = metadata.get(PROVIDER_EXECUTION_REQUEST_METADATA_KEY)
    if raw is None:
        return None
    if isinstance(raw, ProviderExecutionRequest):
        return raw
    if not isinstance(raw, dict):
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_MANIFEST_MISMATCH,
            "provider_execution_request must be a dict",
        )
    manifest_raw = raw.get("image_manifest")
    if not isinstance(manifest_raw, dict):
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_MANIFEST_MISMATCH,
            "provider_execution_request.image_manifest missing",
        )
    try:
        manifest = ExecutionImageManifest.from_dict(manifest_raw)
    except ExecutionImageManifestError as exc:
        raise ProviderImageExecutionError(
            PROVIDER_IMAGE_MANIFEST_MISMATCH,
            str(exc),
        ) from exc
    # Images are rebuilt at strategy boundary; metadata carries manifest + job context only.
    return None


def attach_provider_execution_request(
    metadata: dict[str, Any],
    request: ProviderExecutionRequest,
) -> None:
    """Store serializable contract snapshot (manifest + image identity, not raw bytes)."""
    metadata[PROVIDER_EXECUTION_REQUEST_METADATA_KEY] = request.to_dict()
    metadata["_provider_execution_request_object"] = request
