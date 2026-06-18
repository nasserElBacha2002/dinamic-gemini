"""Phase 4.4 — Cross-provider logical payload parity."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
)
from src.llm.vision_multimodal_payload import (
    build_anthropic_vision_from_serialized,
    build_gemini_contents_from_serialized,
    build_openai_vision_from_serialized,
)
from src.llm.prompt_composer.enrichments import enrich_prompt_with_execution_manifest
from src.pipeline.services.execution_image_manifest_payload import (
    bind_provider_payload_from_manifest,
    primary_lookups_from_acquired,
)
from src.pipeline.services.provider_execution_request import build_provider_execution_request
from src.pipeline.services.provider_payload_serialization import (
    logical_projection_from_serialized,
    serialize_provider_images,
)


def _serialized():
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
        reference_image_by_source_id={"ref-1": Image.new("RGB", (2, 2), color=(1, 2, 3))},
    )
    prompt, projection = enrich_prompt_with_execution_manifest("prompt", manifest)
    req = build_provider_execution_request(
        job_id="job-1",
        prompt=prompt,
        manifest=manifest,
        bound_payload=bound,
    )
    return serialize_provider_images(req, prompt_projection=projection)


def test_cross_provider_same_logical_projection() -> None:
    serialized = _serialized()
    expected = logical_projection_from_serialized(serialized)

    openai_parts, openai_order = build_openai_vision_from_serialized(
        main_prompt_text="P",
        serialized=serialized,
    )
    anthropic_parts, anthropic_order = build_anthropic_vision_from_serialized(
        main_prompt_text="P",
        serialized=serialized,
    )
    gemini_contents, gemini_order = build_gemini_contents_from_serialized(
        main_prompt_text="P",
        serialized=serialized,
    )

    def image_order(meta: list[dict]) -> list[list[str]]:
        return [
            [e["manifest_entry_id"], e["kind"].replace("primary_evidence", "primary_evidence")]
            for e in meta
            if e.get("kind") in ("reference", "primary_evidence")
        ]

    openai_proj = [
        [e["manifest_entry_id"], "reference_image" if e["kind"] == "reference" else "primary_evidence"]
        for e in openai_order
        if e.get("kind") in ("reference", "primary_evidence")
    ]
    anthropic_proj = [
        [e["manifest_entry_id"], "reference_image" if e["kind"] == "reference" else "primary_evidence"]
        for e in anthropic_order
        if e.get("kind") in ("reference", "primary_evidence")
    ]
    gemini_proj = [
        [e["manifest_entry_id"], "reference_image" if e["kind"] == "reference" else "primary_evidence"]
        for e in gemini_order
        if e.get("kind") in ("reference", "primary_evidence")
    ]

    assert expected == openai_proj == anthropic_proj == gemini_proj
    assert len(openai_parts) >= 7
    assert len(anthropic_parts) >= 7
    assert len(gemini_contents) >= 7
