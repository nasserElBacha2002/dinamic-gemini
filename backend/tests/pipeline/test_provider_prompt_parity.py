"""Phase 4.4 corrections — prompt composition parity."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
)
from src.domain.prompt_image_projection import PromptImageProjection
from src.llm.prompt_composer.enrichments import enrich_prompt_with_execution_manifest
from src.pipeline.services.execution_image_manifest_payload import (
    bind_provider_payload_from_manifest,
    primary_lookups_from_acquired,
)
from src.pipeline.services.provider_execution_errors import PROVIDER_IMAGE_MANIFEST_MISMATCH
from src.pipeline.services.provider_execution_request import build_provider_execution_request
from src.pipeline.services.provider_payload_serialization import (
    serialize_provider_images,
    validate_execution_projections_parity,
)


def _bundle():
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
    nds = [np.zeros((2, 2, 3), dtype=np.uint8), np.ones((2, 2, 3), dtype=np.uint8)]
    path_by, nd_by = primary_lookups_from_acquired(paths, ["asset-1", "asset-2"], nds)
    bound = bind_provider_payload_from_manifest(
        manifest,
        primary_path_by_source_id=path_by,
        primary_nd_by_source_id=nd_by,
        reference_image_by_source_id={"ref-1": object()},
    )
    prompt, projection = enrich_prompt_with_execution_manifest("BASE", manifest)
    req = build_provider_execution_request(
        job_id="job-1", prompt=prompt, manifest=manifest, bound_payload=bound
    )
    serialized = serialize_provider_images(req, prompt_projection=projection)
    return manifest, prompt, projection, req, serialized


def test_prompt_text_lists_each_id_once_in_correct_section() -> None:
    _, prompt, projection, _, _ = _bundle()
    assert "PRIMARY EVIDENCE IMAGES" in prompt
    assert "REFERENCE IMAGES" in prompt
    assert "- IMG_001 " in prompt
    assert "- IMG_002 " in prompt
    assert "- REF_001 " in prompt
    assert projection.primary_manifest_entry_ids == ("IMG_001", "IMG_002")
    assert projection.reference_manifest_entry_ids == ("REF_001",)


def test_missing_prompt_id_fails_parity() -> None:
    manifest, _, projection, req, serialized = _bundle()
    bad_projection = PromptImageProjection(
        ordered_manifest_entry_ids=("REF_001", "IMG_001"),
        primary_manifest_entry_ids=("IMG_001",),
        reference_manifest_entry_ids=("REF_001",),
        manifest_version=manifest.version,
    )
    with pytest.raises(Exception, match=PROVIDER_IMAGE_MANIFEST_MISMATCH):
        validate_execution_projections_parity(
            manifest,
            prompt_projection=bad_projection,
            provider_request=req,
            serialized_payload_projection=serialized,
        )
