"""Phase 4.3 — ExecutionImageManifest builder."""

from __future__ import annotations

import pytest

from src.domain.execution_image_manifest import (
    ExcludedExecutionImage,
    ExecutionImageManifestError,
    ExecutionImageRole,
    ImageExclusionReason,
)
from src.pipeline.services.execution_image_manifest_builder import (
    ManifestPrimaryCandidate,
    ManifestReferenceCandidate,
    build_execution_image_manifest,
    exclusions_from_acquisition_metadata,
)


def test_builder_orders_references_before_primaries() -> None:
    manifest = build_execution_image_manifest(
        job_id="job-1",
        primary_candidates=[
            ManifestPrimaryCandidate("asset-1", "asset-1", "a1.jpg"),
            ManifestPrimaryCandidate("asset-2", "asset-2", "a2.jpg"),
        ],
        reference_candidates=[
            ManifestReferenceCandidate("ref-1", "ref-1", "r1.jpg", loaded=True),
        ],
    )
    ordered = manifest.ordered_entries()
    assert ordered[0].role == ExecutionImageRole.REFERENCE_IMAGE
    assert ordered[0].manifest_entry_id == "REF_001"
    assert ordered[1].manifest_entry_id == "IMG_001"
    assert ordered[2].manifest_entry_id == "IMG_002"
    assert manifest.primary_source_image_ids() == ("asset-1", "asset-2")


def test_frame_cap_exclusion_recorded() -> None:
    manifest = build_execution_image_manifest(
        job_id="job-1",
        primary_candidates=[ManifestPrimaryCandidate("asset-1", "asset-1", "a1.jpg")],
        reference_candidates=[],
        excluded=[
            ExcludedExecutionImage(
                source_asset_id="asset-dropped",
                source_image_id="asset-dropped",
                reason=ImageExclusionReason.FRAME_CAP,
            )
        ],
    )
    assert manifest.excluded_source_image_ids() == frozenset({"asset-dropped"})
    assert "asset-dropped" not in manifest.primary_source_image_ids()


def test_unloaded_reference_excluded() -> None:
    manifest = build_execution_image_manifest(
        job_id="job-1",
        primary_candidates=[ManifestPrimaryCandidate("asset-1", "asset-1", "a1.jpg")],
        reference_candidates=[
            ManifestReferenceCandidate("ref-missing", "ref-missing", "r.jpg", loaded=False),
        ],
    )
    assert manifest.reference_entries() == ()
    reasons = [e.reason for e in manifest.excluded_entries]
    assert ImageExclusionReason.MISSING_STORAGE_OBJECT in reasons


def test_no_primary_candidates_fails() -> None:
    with pytest.raises(ExecutionImageManifestError, match="PRIMARY_EVIDENCE"):
        build_execution_image_manifest(
            job_id="job-1",
            primary_candidates=[],
            reference_candidates=[
                ManifestReferenceCandidate("ref-1", "ref-1", "r.jpg", loaded=True),
            ],
        )


def test_exclusions_from_acquisition_metadata_parses_records() -> None:
    exclusions = exclusions_from_acquisition_metadata(
        {
            "manifest_exclusions": [
                {
                    "source_image_id": "asset-x",
                    "source_asset_id": "asset-x",
                    "reason": "decode_failed",
                }
            ]
        }
    )
    assert len(exclusions) == 1
    assert exclusions[0].reason == ImageExclusionReason.DECODE_FAILED


def test_duplicate_primary_candidate_first_wins_later_excluded() -> None:
    manifest = build_execution_image_manifest(
        job_id="job-1",
        primary_candidates=[
            ManifestPrimaryCandidate("asset-1", "asset-1", "a1.jpg"),
            ManifestPrimaryCandidate("asset-1", "asset-1", "a1-dup.jpg"),
        ],
        reference_candidates=[],
    )
    assert manifest.primary_source_image_ids() == ("asset-1",)
    dup_reasons = [
        e.reason
        for e in manifest.excluded_entries
        if e.source_image_id == "asset-1" and e.reason == ImageExclusionReason.DUPLICATE
    ]
    assert len(dup_reasons) == 1
