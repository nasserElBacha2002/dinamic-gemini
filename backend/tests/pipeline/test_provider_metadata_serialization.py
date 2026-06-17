"""Phase 4.4 corrections — metadata must remain JSON-serializable."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
)
from src.domain.prompt_image_projection import COMPOSITION_KEY_PROMPT_IMAGE_PROJECTION
from src.llm.prompt_composer.enrichments import enrich_prompt_with_execution_manifest
from src.llm.types import IMAGE_EXECUTION_CONTRACT_CANONICAL_MANIFEST, LLMRequest
from src.pipeline.services.execution_image_manifest_payload import (
    bind_provider_payload_from_manifest,
    primary_lookups_from_acquired,
)
from src.pipeline.services.provider_execution_request import (
    attach_provider_execution_request_snapshot,
    build_provider_execution_request,
)


def _request() -> LLMRequest:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(
            ExecutionImageEntry(
                manifest_entry_id="IMG_001",
                source_asset_id="asset-1",
                source_image_id="asset-1",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=1,
                storage_reference="a.jpg",
            ),
        ),
        excluded_entries=(),
    )
    paths = [Path("a.jpg")]
    nds = [np.zeros((2, 2, 3), dtype=np.uint8)]
    path_by, nd_by = primary_lookups_from_acquired(paths, ["asset-1"], nds)
    bound = bind_provider_payload_from_manifest(
        manifest,
        primary_path_by_source_id=path_by,
        primary_nd_by_source_id=nd_by,
        reference_image_by_source_id={},
    )
    prompt, projection = enrich_prompt_with_execution_manifest("prompt", manifest)
    provider_req = build_provider_execution_request(
        job_id="job-1",
        prompt=prompt,
        manifest=manifest,
        bound_payload=bound,
    )
    meta: dict = {
        "prompt_composition": {
            COMPOSITION_KEY_PROMPT_IMAGE_PROJECTION: projection.to_dict(),
        }
    }
    attach_provider_execution_request_snapshot(meta, provider_req)
    return LLMRequest(
        job_id="job-1",
        frames=paths,
        frame_refs=["asset-1"],
        prompt=prompt,
        schema_version="v2.1",
        metadata=meta,
        frames_nd=nds,
        provider_execution_request=provider_req,
        canonical_provider_payload_required=True,
        image_execution_contract=IMAGE_EXECUTION_CONTRACT_CANONICAL_MANIFEST,
    )


def test_metadata_is_json_serializable() -> None:
    req = _request()
    json.dumps(req.metadata)


def test_no_runtime_objects_in_metadata() -> None:
    req = _request()
    assert "_provider_execution_request_object" not in req.metadata
    assert "_serialized_multimodal_payload" not in req.metadata


def test_runtime_on_llm_request_not_metadata() -> None:
    req = _request()
    assert req.provider_execution_request is not None
    assert isinstance(req.frames_nd[0], np.ndarray)
