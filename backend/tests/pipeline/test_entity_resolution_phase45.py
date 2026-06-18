"""Phase 4.5 — entity resolution evidence normalization integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.domain.entity import Entity
from src.domain.execution_image_manifest import (
    COMPOSITION_KEY_EXECUTION_IMAGE_MANIFEST,
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
    manifest_composition_projection,
)
from src.domain.manifest_evidence_resolution import (
    WARNING_MANIFEST_INVALID,
    WARNING_MANIFEST_UNAVAILABLE,
    apply_evidence_resolution_to_entities,
)
from src.domain.traceability import (
    TraceabilityStatus,
    WARNING_UNVALIDATED,
    apply_traceability_validation,
    extract_sent_image_ids_from_composition,
    resolve_has_valid_evidence_displayable,
)
from src.parsing.global_analysis_parser import parse_entities
from src.jobs.image_identity import JobImage
from src.pipeline.context.run_context import RunContext
from src.pipeline.stages.analysis_stage import AnalysisStageResult
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage


def _manifest_composition() -> dict:
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
    return manifest_composition_projection(manifest)


def _parse_and_resolve(payload: dict) -> list[Entity]:
    entities = parse_entities(payload, job_id="job-1")
    composition = _manifest_composition()
    apply_evidence_resolution_to_entities(entities, composition=composition)
    sent = extract_sent_image_ids_from_composition(composition) or frozenset()
    apply_traceability_validation(entities, sent, sent_metadata_available=True)
    return entities


def test_source_image_id_is_stable_after_normalization() -> None:
    payload = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "manifest_entry_id": "IMG_001",
            }
        ],
    }
    entities = _parse_and_resolve(payload)
    assert entities[0].source_image_id == "asset-1"
    assert entities[0].resolved_manifest_entry_id == "IMG_001"
    assert entities[0].manifest_entry_id == "IMG_001"
    assert entities[0].traceability_status == TraceabilityStatus.VALID.value


def test_raw_manifest_entry_id_not_copied_into_source_image_id() -> None:
    payload = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "manifest_entry_id": "IMG_001",
            }
        ],
    }
    entities = parse_entities(payload, job_id="job-1")
    assert entities[0].source_image_id is None
    entities = _parse_and_resolve(payload)
    assert entities[0].source_image_id == "asset-1"
    assert entities[0].source_image_id != "IMG_001"


def test_corrupt_manifest_marks_unvalidated() -> None:
    entities = parse_entities(
        {
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "has_boxes": True,
                    "confidence": 0.9,
                    "manifest_entry_id": "IMG_001",
                }
            ],
        },
        job_id="job-1",
    )
    apply_evidence_resolution_to_entities(
        entities,
        composition={COMPOSITION_KEY_EXECUTION_IMAGE_MANIFEST: {"version": 1, "entries": "bad"}},
    )
    assert entities[0].traceability_status == TraceabilityStatus.UNVALIDATED.value
    assert entities[0].traceability_warning == WARNING_MANIFEST_INVALID


def test_manifest_required_true_missing_manifest_unvalidated() -> None:
    entities = parse_entities(
        {
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "has_boxes": True,
                    "confidence": 0.9,
                    "manifest_entry_id": "IMG_001",
                }
            ],
        },
        job_id="job-1",
    )
    apply_evidence_resolution_to_entities(
        entities,
        composition={},
        manifest_required=True,
    )
    assert entities[0].traceability_status == TraceabilityStatus.UNVALIDATED.value
    assert entities[0].traceability_warning == WARNING_MANIFEST_UNAVAILABLE
    assert entities[0].source_image_id is None
    assert entities[0].manifest_entry_id == "IMG_001"


def test_manifest_required_true_corrupt_manifest_unvalidated() -> None:
    entities = parse_entities(
        {
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "has_boxes": True,
                    "confidence": 0.9,
                    "manifest_entry_id": "IMG_001",
                }
            ],
        },
        job_id="job-1",
    )
    apply_evidence_resolution_to_entities(
        entities,
        composition={COMPOSITION_KEY_EXECUTION_IMAGE_MANIFEST: {"version": 1, "entries": "bad"}},
        manifest_required=True,
    )
    assert entities[0].traceability_status == TraceabilityStatus.UNVALIDATED.value
    assert entities[0].source_image_id is None


def test_manifest_required_false_legacy_deferred_without_manifest() -> None:
    """Legacy path: without manifest requirement, resolution defers (no stable source_image_id)."""
    entities = parse_entities(
        {
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "has_boxes": True,
                    "confidence": 0.9,
                    "source_image_id": "asset-1",
                }
            ],
        },
        job_id="job-1",
    )
    apply_evidence_resolution_to_entities(
        entities,
        composition={},
        manifest_required=False,
    )
    assert entities[0].source_image_id is None
    assert entities[0].raw_source_image_id == "asset-1"
    assert entities[0].traceability_status is None


def _manifest_composition_with_ref() -> dict:
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
                storage_reference="a.jpg",
            ),
        ),
        excluded_entries=(),
    )
    return manifest_composition_projection(manifest)


def test_invalid_reference_has_no_valid_evidence() -> None:
    payload = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "manifest_entry_id": "REF_001",
            }
        ],
    }
    entities = parse_entities(payload, job_id="job-1")
    composition = _manifest_composition_with_ref()
    apply_evidence_resolution_to_entities(entities, composition=composition, manifest_required=True)
    sent = extract_sent_image_ids_from_composition(composition) or frozenset()
    apply_traceability_validation(entities, sent, sent_metadata_available=True)
    ent = entities[0]
    assert ent.traceability_status == TraceabilityStatus.INVALID.value
    assert ent.source_image_id is None
    assert ent.resolved_manifest_entry_id == "REF_001"
    assert resolve_has_valid_evidence_displayable(
        traceability_status=ent.traceability_status,
        source_image_id=ent.source_image_id,
        persisted_has_valid_evidence=False,
    ) is False


def test_raw_legacy_id_unvalidated_does_not_populate_source_image_id() -> None:
    ent = parse_entities(
        {
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "has_boxes": True,
                    "confidence": 0.9,
                    "source_image_id": "filename.jpg",
                }
            ],
        },
        job_id="job-1",
    )[0]
    apply_traceability_validation(
        [ent],
        frozenset(),
        sent_metadata_available=False,
    )
    assert ent.source_image_id is None
    assert ent.raw_source_image_id == "filename.jpg"
    assert ent.traceability_status == TraceabilityStatus.UNVALIDATED.value
    assert ent.traceability_warning == WARNING_UNVALIDATED


def test_photo_v3_stage_manifest_required_missing_composition_unvalidated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Active photo V3 jobs pass manifest_required=True; missing manifest cannot become VALID."""
    context = MagicMock(spec=RunContext)
    context.job_id = "job-1"
    context.logger = MagicMock()
    context.run_dir = tmp_path
    job_input = MagicMock()
    job_input.input_type = "photos"
    context.job_input = job_input

    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.load_job_images_from_manifest",
        lambda _mp, _pd: [JobImage("asset-1", "a.jpg", 1, "a.jpg")],
    )
    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.resolve_manifest_path",
        lambda _rd, _ji: Path("/fake/manifest.json"),
    )
    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.photos_dir_relative_for_manifest",
        lambda _ji: "photos",
    )

    analysis_result = AnalysisStageResult(
        parsed_json={
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "has_boxes": True,
                    "confidence": 0.9,
                    "manifest_entry_id": "IMG_001",
                }
            ],
        },
        provider_name="gemini",
        prompt_composition={"frames_sent_ids": ["asset-1"]},
    )

    resolved = EntityResolutionStage().run(context, analysis_result)
    ent = resolved.entities[0]
    assert ent.traceability_status == TraceabilityStatus.UNVALIDATED.value
    assert ent.traceability_warning == WARNING_MANIFEST_UNAVAILABLE
    assert ent.source_image_id is None
    assert ent.manifest_entry_id == "IMG_001"
