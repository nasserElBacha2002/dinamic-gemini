"""Phase 4.2 — traceability validation and evidence display eligibility."""

from __future__ import annotations

from src.domain.entity import Entity
from src.domain.traceability import (
    TRACEABILITY_INVALID,
    TRACEABILITY_MISSING,
    TRACEABILITY_UNVALIDATED,
    TRACEABILITY_VALID,
    WARNING_MISSING_ID,
    WARNING_NOT_IN_SENT,
    WARNING_REFERENCE_IMAGE,
    WARNING_UNVALIDATED,
    apply_traceability_validation,
    extract_sent_image_ids_from_composition,
    is_traceability_evidence_displayable,
    resolve_has_valid_evidence_displayable,
)


def test_valid_when_id_in_final_sent_set() -> None:
    ent = Entity(
        entity_uid="j_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        source_image_id="asset-1",
    )
    apply_traceability_validation(
        [ent],
        frozenset({"asset-1"}),
        manifest_image_ids=frozenset({"asset-1", "asset-2"}),
        sent_metadata_available=True,
    )
    assert ent.traceability_status == TRACEABILITY_VALID
    assert ent.traceability_warning is None
    assert is_traceability_evidence_displayable(
        traceability_status=ent.traceability_status,
        source_image_id=ent.source_image_id,
    )


def test_invalid_when_id_only_in_preliminary_manifest() -> None:
    ent = Entity(
        entity_uid="j_E2",
        entity_type="PALLET",
        model_entity_id="E2",
        source_image_id="asset-dropped",
    )
    apply_traceability_validation(
        [ent],
        frozenset({"asset-1"}),
        manifest_image_ids=frozenset({"asset-1", "asset-dropped"}),
        sent_metadata_available=True,
    )
    assert ent.traceability_status == TRACEABILITY_INVALID
    assert ent.traceability_warning == WARNING_NOT_IN_SENT


def test_missing_when_provider_returns_no_id() -> None:
    ent = Entity(
        entity_uid="j_E3",
        entity_type="PALLET",
        model_entity_id="E3",
        source_image_id=None,
    )
    apply_traceability_validation(
        [ent],
        frozenset({"asset-1"}),
        sent_metadata_available=True,
    )
    assert ent.traceability_status == TRACEABILITY_MISSING
    assert ent.traceability_warning == WARNING_MISSING_ID


def test_unvalidated_when_sent_metadata_unavailable() -> None:
    ent = Entity(
        entity_uid="j_E4",
        entity_type="PALLET",
        model_entity_id="E4",
        source_image_id="asset-1",
    )
    apply_traceability_validation(
        [ent],
        frozenset(),
        manifest_image_ids=frozenset({"asset-1"}),
        sent_metadata_available=False,
    )
    assert ent.traceability_status == TRACEABILITY_UNVALIDATED
    assert ent.traceability_warning == WARNING_UNVALIDATED
    assert not is_traceability_evidence_displayable(
        traceability_status=ent.traceability_status,
        source_image_id=ent.source_image_id,
    )


def test_no_manifest_fallback_to_valid() -> None:
    """Preliminary manifest membership must not promote to VALID without sent metadata."""
    ent = Entity(
        entity_uid="j_E5",
        entity_type="PALLET",
        model_entity_id="E5",
        source_image_id="asset-only-in-manifest",
    )
    apply_traceability_validation(
        [ent],
        frozenset(),
        manifest_image_ids=frozenset({"asset-only-in-manifest"}),
        sent_metadata_available=False,
    )
    assert ent.traceability_status == TRACEABILITY_UNVALIDATED


def test_reference_image_id_is_invalid() -> None:
    ent = Entity(
        entity_uid="j_E6",
        entity_type="PALLET",
        model_entity_id="E6",
        source_image_id="ref-1",
    )
    apply_traceability_validation(
        [ent],
        frozenset({"asset-1", "ref-1"}),
        reference_image_ids=frozenset({"ref-1"}),
        sent_metadata_available=True,
    )
    assert ent.traceability_status == TRACEABILITY_INVALID
    assert ent.traceability_warning == WARNING_REFERENCE_IMAGE


def test_extract_sent_image_ids_prefers_frames_sent_ids() -> None:
    ids = extract_sent_image_ids_from_composition(
        {"frames_sent_ids": ["a", "b"], "prompt_listed_image_ids": ["x"]}
    )
    assert ids == frozenset({"a", "b"})


def test_extract_sent_image_ids_returns_none_when_missing() -> None:
    assert extract_sent_image_ids_from_composition({}) is None
    assert extract_sent_image_ids_from_composition(None) is None


def test_prompt_listed_ids_are_not_authoritative_without_frames_sent_ids() -> None:
    composition = {
        "prompt_listed_image_ids": ["asset-1"],
    }
    assert extract_sent_image_ids_from_composition(composition) is None


def test_empty_frames_sent_ids_returns_none_even_with_prompt_listed() -> None:
    composition = {
        "frames_sent_ids": [],
        "prompt_listed_image_ids": ["asset-1", "asset-2"],
    }
    assert extract_sent_image_ids_from_composition(composition) is None


def test_malformed_frames_sent_ids_returns_none() -> None:
    assert extract_sent_image_ids_from_composition({"frames_sent_ids": "asset-1"}) is None
    assert extract_sent_image_ids_from_composition({"frames_sent_ids": {}}) is None


def test_extract_sent_ids_prefers_canonical_manifest_over_prompt_listed() -> None:
    composition = {
        "prompt_listed_image_ids": ["IMG_001"],
        "execution_image_manifest": {
            "job_id": "job-1",
            "version": 1,
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
        },
    }
    assert extract_sent_image_ids_from_composition(composition) == frozenset({"asset-1"})


def test_corrupt_manifest_key_fails_closed_no_frames_sent_fallback() -> None:
    composition = {
        "execution_image_manifest": {"job_id": "job-1", "version": 99, "entries": []},
        "frames_sent_ids": ["asset-1"],
        "prompt_listed_image_ids": ["IMG_001"],
    }
    assert extract_sent_image_ids_from_composition(composition) is None


def test_resolve_has_valid_evidence_fail_closed_matrix() -> None:
    assert resolve_has_valid_evidence_displayable(
        traceability_status=TRACEABILITY_VALID,
        source_image_id="asset-1",
        persisted_has_valid_evidence=False,
    ) is False
    assert resolve_has_valid_evidence_displayable(
        traceability_status=TRACEABILITY_VALID,
        source_image_id="asset-1",
        persisted_has_valid_evidence=None,
    ) is False
    assert resolve_has_valid_evidence_displayable(
        traceability_status=TRACEABILITY_INVALID,
        source_image_id="asset-1",
        persisted_has_valid_evidence=True,
    ) is False
    assert resolve_has_valid_evidence_displayable(
        traceability_status=TRACEABILITY_VALID,
        source_image_id=None,
        persisted_has_valid_evidence=True,
    ) is False
    assert resolve_has_valid_evidence_displayable(
        traceability_status=TRACEABILITY_VALID,
        source_image_id="asset-1",
        persisted_has_valid_evidence=True,
    ) is True
    assert resolve_has_valid_evidence_displayable(
        traceability_status=TRACEABILITY_VALID,
        source_image_id="asset-1",
        persisted_has_valid_evidence="true",
    ) is False
