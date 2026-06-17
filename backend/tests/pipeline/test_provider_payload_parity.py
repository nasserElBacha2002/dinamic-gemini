"""Phase 4.4 — Provider payload serialization and parity validation."""

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
    bind_provider_payload_from_manifest,
    primary_lookups_from_acquired,
)
from src.pipeline.services.provider_execution_errors import (
    PROVIDER_IMAGE_MANIFEST_MISMATCH,
    ProviderImageExecutionError,
)
from src.pipeline.services.provider_execution_request import build_provider_execution_request
from src.pipeline.services.provider_payload_serialization import (
    logical_projection_from_serialized,
    serialize_provider_images,
    validate_prompt_payload_manifest_parity,
)


def _fixture() -> tuple[ExecutionImageManifest, object]:
    manifest = ExecutionImageManifest(
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
    paths = [Path("a1.jpg"), Path("a2.jpg")]
    refs = ["asset-1", "asset-2"]
    nds = [np.zeros((2, 2, 3), dtype=np.uint8), np.ones((2, 2, 3), dtype=np.uint8)]
    path_by, nd_by = primary_lookups_from_acquired(paths, refs, nds)
    bound = bind_provider_payload_from_manifest(
        manifest,
        primary_path_by_source_id=path_by,
        primary_nd_by_source_id=nd_by,
        reference_image_by_source_id={"ref-1": object()},
    )
    req = build_provider_execution_request(
        job_id="job-1",
        prompt="p",
        manifest=manifest,
        bound_payload=bound,
    )
    return manifest, serialize_provider_images(req)


def test_exact_manifest_entry_order() -> None:
    manifest, serialized = _fixture()
    assert [e.manifest_entry_id for e in serialized.entries] == [
        "REF_001",
        "IMG_001",
        "IMG_002",
    ]
    assert logical_projection_from_serialized(serialized) == [
        ["REF_001", "reference_image"],
        ["IMG_001", "primary_evidence"],
        ["IMG_002", "primary_evidence"],
    ]


def test_provider_positions_contiguous_from_zero() -> None:
    _, serialized = _fixture()
    positions = [e.provider_image_position for e in serialized.entries]
    assert positions == [0, 1, 2]


def test_parity_rejects_reordered_payload() -> None:
    manifest, serialized = _fixture()
    from src.pipeline.services.provider_payload_serialization import SerializedImagePayloadEntry

    reordered = (serialized.entries[1], serialized.entries[0], serialized.entries[2])
    from src.pipeline.services.provider_payload_serialization import SerializedMultimodalPayload

    bad = SerializedMultimodalPayload(
        entries=reordered,
        provider_image_manifest_order=serialized.provider_image_manifest_order,
        logical_projection=serialized.logical_projection,
    )
    prompt_proj = [
        (e.manifest_entry_id, e.role.value, e.payload_ordinal)
        for e in manifest.ordered_entries()
    ]
    with pytest.raises(ProviderImageExecutionError, match=PROVIDER_IMAGE_MANIFEST_MISMATCH):
        validate_prompt_payload_manifest_parity(
            manifest,
            prompt_projection=prompt_proj,
            serialized_payload_projection=bad,
        )
