"""Phase 4.3 corrections — manifest-bound provider payload."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageManifestError,
    ExecutionImageRole,
)
from src.llm.vision_multimodal_payload import build_openai_vision_content_parts
from src.pipeline.services.execution_image_manifest_payload import (
    bind_provider_payload_from_manifest,
    primary_lookups_from_acquired,
    reference_lookup_from_visual_bundle,
    validate_provider_lists_against_manifest,
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


def test_bind_provider_payload_orders_references_then_primaries() -> None:
    paths = [Path("a1.jpg"), Path("a2.jpg")]
    refs = ["asset-1", "asset-2"]
    nds = [np.zeros((2, 2, 3), dtype=np.uint8), np.ones((2, 2, 3), dtype=np.uint8)]
    path_by, nd_by = primary_lookups_from_acquired(paths, refs, nds)
    ref_img = object()
    payload = bind_provider_payload_from_manifest(
        _manifest(),
        primary_path_by_source_id=path_by,
        primary_nd_by_source_id=nd_by,
        reference_image_by_source_id={"ref-1": ref_img},
    )
    assert payload.reference_image_ids == ("ref-1",)
    assert payload.context_images == (ref_img,)
    assert payload.frame_refs == ("asset-1", "asset-2")
    assert payload.frame_paths == (paths[0], paths[1])


def test_bind_fails_when_primary_image_missing() -> None:
    path_by, nd_by = primary_lookups_from_acquired(
        [Path("a1.jpg")], ["asset-1"], [np.zeros((2, 2, 3))]
    )
    with pytest.raises(ExecutionImageManifestError, match="primary image not bound"):
        bind_provider_payload_from_manifest(
            _manifest(),
            primary_path_by_source_id=path_by,
            primary_nd_by_source_id=nd_by,
            reference_image_by_source_id={"ref-1": object()},
        )


def test_adapter_validation_rejects_reordered_frame_refs() -> None:
    manifest = _manifest()
    with pytest.raises(ExecutionImageManifestError, match="frame_refs mismatch"):
        validate_provider_lists_against_manifest(
            manifest,
            frame_refs=["asset-2", "asset-1"],
            reference_image_ids=["ref-1"],
        )


def test_openai_builder_validates_against_manifest_in_metadata() -> None:
    manifest = _manifest()
    meta = {
        "prompt_composition": {
            "execution_image_manifest": manifest.to_dict(),
            "frames_sent_ids": list(manifest.primary_source_image_ids()),
            "reference_image_ids": list(manifest.reference_source_image_ids()),
        }
    }
    parts, order = build_openai_vision_content_parts(
        main_prompt_text="prompt",
        context_images=[object()],
        reference_image_ids=["ref-1"],
        primary_frames_nd=[np.zeros((2, 2, 3)), np.zeros((2, 2, 3))],
        frame_refs=["asset-1", "asset-2"],
        request_metadata=meta,
    )
    assert parts
    assert order
    image_kinds = [e["kind"] for e in order if e.get("kind") in ("reference", "primary_evidence")]
    assert image_kinds == ["reference", "primary_evidence", "primary_evidence"]


def test_openai_builder_rejects_manifest_order_violation() -> None:
    manifest = _manifest()
    meta = {"prompt_composition": {"execution_image_manifest": manifest.to_dict()}}
    with pytest.raises(ExecutionImageManifestError, match="frame_refs mismatch"):
        build_openai_vision_content_parts(
            main_prompt_text="prompt",
            context_images=[object()],
            reference_image_ids=["ref-1"],
            primary_frames_nd=[np.zeros((2, 2, 3))],
            frame_refs=["asset-2"],
            request_metadata=meta,
        )


def test_reference_lookup_requires_parallel_lists() -> None:
    with pytest.raises(ExecutionImageManifestError, match="misaligned"):
        reference_lookup_from_visual_bundle([object()], ["a", "b"])
