"""Phase 4.5 — raw evidence extraction in global analysis parser."""

from __future__ import annotations

from src.parsing.global_analysis_parser import parse_entities


def _payload(entity: dict) -> dict:
    return {"total_entities_detected": 1, "entities": [entity]}


def test_parser_preserves_manifest_entry_id_only() -> None:
    entities = parse_entities(
        _payload(
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "manifest_entry_id": "IMG_001",
            }
        ),
        job_id="job-1",
    )
    assert entities[0].manifest_entry_id == "IMG_001"
    assert entities[0].raw_source_image_id is None
    assert entities[0].source_image_id is None


def test_parser_preserves_legacy_source_image_id_only() -> None:
    entities = parse_entities(
        _payload(
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "source_image_id": "asset-1",
            }
        ),
        job_id="job-1",
    )
    assert entities[0].manifest_entry_id is None
    assert entities[0].raw_source_image_id == "asset-1"
    assert entities[0].source_image_id is None


def test_parser_preserves_both_evidence_fields() -> None:
    entities = parse_entities(
        _payload(
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "manifest_entry_id": "IMG_001",
                "source_image_id": "asset-1",
            }
        ),
        job_id="job-1",
    )
    assert entities[0].manifest_entry_id == "IMG_001"
    assert entities[0].raw_source_image_id == "asset-1"
    assert entities[0].source_image_id is None


def test_parser_blank_evidence_fields_become_missing() -> None:
    entities = parse_entities(
        _payload(
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "manifest_entry_id": "  ",
                "source_image_id": "",
            }
        ),
        job_id="job-1",
    )
    assert entities[0].manifest_entry_id is None
    assert entities[0].raw_source_image_id is None
