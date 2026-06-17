"""Phase 4.4 — ProviderExecutionRequest contract tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
)
from src.pipeline.services.execution_image_manifest_payload import (
    ManifestBoundProviderPayload,
    bind_provider_payload_from_manifest,
    primary_lookups_from_acquired,
)
from src.pipeline.services.provider_execution_errors import (
    PROVIDER_IMAGE_MANIFEST_MISMATCH,
    PROVIDER_IMAGE_RESOURCE_MISSING,
    ProviderImageExecutionError,
)
from src.pipeline.services.provider_execution_request import (
    build_provider_execution_request,
    validate_provider_execution_request,
)


def _manifest() -> ExecutionImageManifest:
    return ExecutionImageManifest(
        job_id="job-1",
        entries=(
            ExecutionImageEntry(
                manifest_entry_id="REF_001",
                source_asset_id="ref-1",
                source_image_id="ref-1",
                role=ExecutionImageRole.REFERENCE_IMAGE,
                payload_ordinal=1,
                storage_reference="ref.jpg",
            ),
            ExecutionImageEntry(
                manifest_entry_id="IMG_001",
                source_asset_id="asset-1",
                source_image_id="asset-1",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=2,
                storage_reference="a1.jpg",
            ),
            ExecutionImageEntry(
                manifest_entry_id="IMG_002",
                source_asset_id="asset-2",
                source_image_id="asset-2",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=3,
                storage_reference="a2.jpg",
            ),
        ),
        excluded_entries=(),
    )


def _bound(manifest: ExecutionImageManifest) -> ManifestBoundProviderPayload:
    paths = [Path("a1.jpg"), Path("a2.jpg")]
    refs = ["asset-1", "asset-2"]
    nds = [np.zeros((2, 2, 3), dtype=np.uint8), np.ones((2, 2, 3), dtype=np.uint8)]
    path_by, nd_by = primary_lookups_from_acquired(paths, refs, nds)
    return bind_provider_payload_from_manifest(
        manifest,
        primary_path_by_source_id=path_by,
        primary_nd_by_source_id=nd_by,
        reference_image_by_source_id={"ref-1": object()},
    )


def test_request_image_order_equals_manifest_order() -> None:
    manifest = _manifest()
    req = build_provider_execution_request(
        job_id="job-1",
        prompt="p",
        manifest=manifest,
        bound_payload=_bound(manifest),
    )
    ids = [img.manifest_entry_id for img in req.ordered_images()]
    assert ids == ["REF_001", "IMG_001", "IMG_002"]


def test_missing_runtime_resource_rejected() -> None:
    manifest = _manifest()
    req = build_provider_execution_request(
        job_id="job-1",
        prompt="p",
        manifest=manifest,
        bound_payload=_bound(manifest),
    )
    from src.pipeline.services.provider_execution_request import (
        ImageRuntimeResource,
        ProviderExecutionImage,
    )

    broken = ProviderExecutionImage(
        manifest_entry_id=req.images[-1].manifest_entry_id,
        source_image_id=req.images[-1].source_image_id,
        source_asset_id=req.images[-1].source_asset_id,
        role=req.images[-1].role,
        payload_ordinal=req.images[-1].payload_ordinal,
        runtime_resource=ImageRuntimeResource(resource=None, is_primary_ndarray=True),
        mime_type="image/jpeg",
    )
    bad_images = req.images[:-1] + (broken,)
    bad_req = type(req)(
        job_id=req.job_id,
        prompt=req.prompt,
        image_manifest=req.image_manifest,
        images=bad_images,
        schema_version=req.schema_version,
        metadata=req.metadata,
    )
    from src.pipeline.services.provider_payload_serialization import serialize_provider_images

    with pytest.raises(ProviderImageExecutionError, match=PROVIDER_IMAGE_RESOURCE_MISSING):
        serialize_provider_images(bad_req)


def test_provider_position_mapping_deterministic() -> None:
    manifest = _manifest()
    req = build_provider_execution_request(
        job_id="job-1",
        prompt="p",
        manifest=manifest,
        bound_payload=_bound(manifest),
    )
    ordinals = [img.payload_ordinal for img in req.ordered_images()]
    assert ordinals == [1, 2, 3]


def test_request_metadata_is_immutable_mapping() -> None:
    manifest = _manifest()
    req = build_provider_execution_request(
        job_id="job-1",
        prompt="p",
        manifest=manifest,
        bound_payload=_bound(manifest),
    )
    with pytest.raises(TypeError):
        req.metadata["mutated"] = True  # type: ignore[index]


def test_count_mismatch_rejected() -> None:
    manifest = _manifest()
    req = build_provider_execution_request(
        job_id="job-1",
        prompt="p",
        manifest=manifest,
        bound_payload=_bound(manifest),
    )
    # Tamper: drop one image from tuple (simulate invalid object)
    bad_images = req.images[:2]
    bad = type(req)(
        job_id=req.job_id,
        prompt=req.prompt,
        image_manifest=req.image_manifest,
        images=bad_images,
        schema_version=req.schema_version,
        metadata=req.metadata,
    )
    with pytest.raises(ProviderImageExecutionError, match=PROVIDER_IMAGE_MANIFEST_MISMATCH):
        validate_provider_execution_request(bad)
