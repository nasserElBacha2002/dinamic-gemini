"""Phase 4.5 — entity resolution evidence normalization integration."""

from __future__ import annotations

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
    apply_evidence_resolution_to_entities,
)
from src.domain.traceability import (
    TraceabilityStatus,
    apply_traceability_validation,
    extract_sent_image_ids_from_composition,
)
from src.parsing.global_analysis_parser import parse_entities


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
