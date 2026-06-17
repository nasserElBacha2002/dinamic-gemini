"""Phase 4.3 — ExecutionImageManifest contract and invariants."""

from __future__ import annotations

import pytest

from src.domain.execution_image_manifest import (
    ExcludedExecutionImage,
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageManifestError,
    ExecutionImageRole,
    ImageExclusionReason,
    manifest_composition_projection,
    validate_execution_image_manifest,
)


def _primary(
    entry_id: str,
    source_id: str,
    ordinal: int,
) -> ExecutionImageEntry:
    return ExecutionImageEntry(
        manifest_entry_id=entry_id,
        source_asset_id=source_id,
        source_image_id=source_id,
        role=ExecutionImageRole.PRIMARY_EVIDENCE,
        payload_ordinal=ordinal,
        storage_reference="a.jpg",
    )


def _reference(entry_id: str, source_id: str, ordinal: int) -> ExecutionImageEntry:
    return ExecutionImageEntry(
        manifest_entry_id=entry_id,
        source_asset_id=source_id,
        source_image_id=source_id,
        role=ExecutionImageRole.REFERENCE_IMAGE,
        payload_ordinal=ordinal,
        storage_reference="ref.jpg",
    )


def test_valid_manifest_with_primary_and_reference() -> None:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(_reference("REF_001", "ref-1", 1), _primary("IMG_001", "asset-1", 2)),
        excluded_entries=(),
    )
    validate_execution_image_manifest(manifest)
    assert manifest.primary_source_image_ids() == ("asset-1",)
    assert manifest.reference_source_image_ids() == ("ref-1",)


def test_duplicate_manifest_entry_id_rejected() -> None:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(_primary("IMG_001", "asset-1", 1), _primary("IMG_001", "asset-2", 2)),
        excluded_entries=(),
    )
    with pytest.raises(ExecutionImageManifestError, match="duplicate manifest_entry_id"):
        validate_execution_image_manifest(manifest)


def test_duplicate_payload_ordinal_rejected() -> None:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(_primary("IMG_001", "asset-1", 1), _primary("IMG_002", "asset-2", 1)),
        excluded_entries=(),
    )
    with pytest.raises(ExecutionImageManifestError, match="duplicate payload_ordinal"):
        validate_execution_image_manifest(manifest)


def test_non_contiguous_ordinals_rejected() -> None:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(_primary("IMG_001", "asset-1", 1), _primary("IMG_002", "asset-2", 3)),
        excluded_entries=(),
    )
    with pytest.raises(ExecutionImageManifestError, match="contiguous"):
        validate_execution_image_manifest(manifest)


def test_missing_source_id_rejected() -> None:
    entry = ExecutionImageEntry(
        manifest_entry_id="IMG_001",
        source_asset_id="asset-1",
        source_image_id="",
        role=ExecutionImageRole.PRIMARY_EVIDENCE,
        payload_ordinal=1,
        storage_reference="a.jpg",
    )
    manifest = ExecutionImageManifest(job_id="job-1", entries=(entry,), excluded_entries=())
    with pytest.raises(ExecutionImageManifestError, match="source_image_id"):
        validate_execution_image_manifest(manifest)


def test_no_primary_entries_rejected() -> None:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(_reference("REF_001", "ref-1", 1),),
        excluded_entries=(),
    )
    with pytest.raises(ExecutionImageManifestError, match="PRIMARY_EVIDENCE"):
        validate_execution_image_manifest(manifest)


def test_excluded_id_cannot_appear_in_active_entries() -> None:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(_primary("IMG_001", "asset-1", 1),),
        excluded_entries=(
            ExcludedExecutionImage(
                source_asset_id="asset-1",
                source_image_id="asset-1",
                reason=ImageExclusionReason.DECODE_FAILED,
            ),
        ),
    )
    with pytest.raises(ExecutionImageManifestError, match="excluded source_image_id"):
        validate_execution_image_manifest(manifest)


def test_primary_cannot_use_ref_prefix() -> None:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(_primary("REF_001", "asset-1", 1),),
        excluded_entries=(),
    )
    with pytest.raises(ExecutionImageManifestError, match="reference manifest_entry_id"):
        validate_execution_image_manifest(manifest)


def test_deterministic_roundtrip_dict() -> None:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(_primary("IMG_001", "asset-1", 1), _primary("IMG_002", "asset-2", 2)),
        excluded_entries=(),
    )
    restored = ExecutionImageManifest.from_dict(manifest.to_dict())
    assert restored.primary_source_image_ids() == ("asset-1", "asset-2")


def test_composition_projection_derives_compatibility_fields() -> None:
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(
            _reference("REF_001", "ref-1", 1),
            _primary("IMG_001", "asset-1", 2),
        ),
        excluded_entries=(),
    )
    proj = manifest_composition_projection(manifest)
    assert proj["frames_sent_ids"] == ["asset-1"]
    assert proj["reference_image_ids"] == ["ref-1"]
    assert "IMG_001" in proj["prompt_listed_image_ids"]
    assert "REF_001" in proj["prompt_listed_image_ids"]


def test_frozen_entry_is_immutable() -> None:
    entry = _primary("IMG_001", "asset-1", 1)
    with pytest.raises(AttributeError):
        entry.source_image_id = "other"  # type: ignore[misc]


def test_from_dict_rejects_unsupported_version() -> None:
    raw = {
        "job_id": "job-1",
        "version": 99,
        "entries": [
            {
                "manifest_entry_id": "IMG_001",
                "source_asset_id": "asset-1",
                "source_image_id": "asset-1",
                "role": "primary_evidence",
                "payload_ordinal": 1,
                "storage_reference": "a.jpg",
            }
        ],
        "excluded_entries": [],
    }
    with pytest.raises(ExecutionImageManifestError, match="unsupported execution_image_manifest version"):
        ExecutionImageManifest.from_dict(raw)


def test_from_dict_requires_version_field() -> None:
    with pytest.raises(ExecutionImageManifestError, match="version is required"):
        ExecutionImageManifest.from_dict({"job_id": "job-1", "entries": []})
