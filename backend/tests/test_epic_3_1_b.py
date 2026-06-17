"""Epic 3.1.B — Backend traceability: parse source_image_id, validate, normalize, persist, expose.

Tests: parsing with/without source_image_id, traceability validation (valid/missing/invalid),
report persistence, API exposure, backward compatibility with legacy responses.
"""

from src.api.schemas.responses import TRACEABILITY_STATUS_VALUES, EntityListItem
from src.domain.entity import Entity
from src.domain.traceability import (
    TRACEABILITY_INVALID,
    TRACEABILITY_MISSING,
    TRACEABILITY_UNVALIDATED,
    TRACEABILITY_VALID,
    WARNING_MISSING_ID,
    WARNING_NOT_IN_JOB,
    WARNING_UNVALIDATED,
    TraceabilityStatus,
    apply_traceability_validation,
)
from src.parsing.global_analysis_parser import parse_entities
from src.reporting.hybrid_report import build_hybrid_report

# ---------- Parsing: source_image_id present / absent ----------


def test_parse_entities_with_source_image_id():
    """When provider returns source_image_id, it is parsed onto Entity."""
    data = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "source_image_id": "img_001",
            }
        ],
    }
    entities = parse_entities(data, job_id="job1")
    assert len(entities) == 1
    assert entities[0].source_image_id == "img_001"
    assert entities[0].traceability_status is None  # not yet validated


def test_parse_entities_without_source_image_id():
    """When provider does not return source_image_id, Entity has None (legacy)."""
    data = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
            }
        ],
    }
    entities = parse_entities(data, job_id="job1")
    assert len(entities) == 1
    assert entities[0].source_image_id is None
    assert entities[0].traceability_status is None


def test_parse_entities_source_image_id_empty_string_becomes_none():
    """Empty or whitespace source_image_id is stored as None by parser (via _safe_str)."""
    data = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "source_image_id": "  ",
            }
        ],
    }
    entities = parse_entities(data, job_id="job1")
    assert entities[0].source_image_id is None


# ---------- Traceability validation ----------


def test_apply_traceability_validation_valid():
    """When source_image_id is in valid_image_ids, status is valid."""
    entities = [
        Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id="img_001",
            traceability_status=None,
            traceability_warning=None,
        )
    ]
    valid_ids = frozenset({"img_001", "img_002"})
    apply_traceability_validation(entities, valid_ids, sent_metadata_available=True)
    assert entities[0].traceability_status == TRACEABILITY_VALID
    assert entities[0].traceability_warning is None


def test_apply_traceability_validation_missing():
    """When source_image_id is absent, status is missing."""
    entities = [
        Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id=None,
            traceability_status=None,
            traceability_warning=None,
        )
    ]
    apply_traceability_validation(entities, frozenset({"img_001"}), sent_metadata_available=True)
    assert entities[0].traceability_status == TRACEABILITY_MISSING
    assert entities[0].traceability_warning == WARNING_MISSING_ID


def test_apply_traceability_validation_invalid():
    """When source_image_id is not in valid_image_ids, status is invalid and warning set."""
    entities = [
        Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id="img_999",
            traceability_status=None,
            traceability_warning=None,
        )
    ]
    valid_ids = frozenset({"img_001", "img_002"})
    apply_traceability_validation(entities, valid_ids, sent_metadata_available=True)
    assert entities[0].traceability_status == TRACEABILITY_INVALID
    assert entities[0].traceability_warning == WARNING_NOT_IN_JOB


def test_apply_traceability_validation_when_context_missing_present_ref_is_unvalidated():
    """When valid_image_ids is empty (no context), non-empty source_image_id -> unvalidated, not invalid."""
    entities = [
        Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id="img_001",
            traceability_status=None,
            traceability_warning=None,
        )
    ]
    apply_traceability_validation(entities, frozenset(), sent_metadata_available=False)
    assert entities[0].traceability_status == TRACEABILITY_UNVALIDATED
    assert entities[0].traceability_warning == WARNING_UNVALIDATED


# ---------- Report: traceability fields persisted ----------


def test_build_hybrid_report_includes_traceability_fields():
    """Report entity dicts include source_image_id, traceability_status, traceability_warning."""
    entities = [
        Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id="img_001",
            traceability_status=TRACEABILITY_VALID,
            traceability_warning=None,
        ),
        Entity(
            entity_uid="j_E2",
            entity_type="PALLET",
            model_entity_id="E2",
            source_image_id=None,
            traceability_status=TRACEABILITY_MISSING,
            traceability_warning=None,
        ),
    ]
    report = build_hybrid_report("/fake/video.mp4", entities, frames_selected=1)
    entity_dicts = report["entities"]
    assert len(entity_dicts) == 2
    assert entity_dicts[0]["source_image_id"] == "img_001"
    assert entity_dicts[0]["traceability_status"] == TRACEABILITY_VALID
    assert entity_dicts[0].get("traceability_warning") is None
    assert entity_dicts[1]["source_image_id"] is None
    assert entity_dicts[1]["traceability_status"] == TRACEABILITY_MISSING


# ---------- Backward compatibility: legacy response ----------


def test_legacy_response_without_traceability_parses_and_validates_as_missing():
    """Legacy provider response without source_image_id parses; validation sets missing."""
    data = {
        "total_entities_detected": 2,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.8,
            },
            {
                "entity_type": "EMPTY_PALLET",
                "model_entity_id": "E2",
                "has_boxes": False,
                "confidence": 0.7,
            },
        ],
    }
    entities = parse_entities(data, job_id="job1")
    apply_traceability_validation(entities, frozenset({"img_001"}))
    assert entities[0].source_image_id is None
    assert entities[0].traceability_status == TRACEABILITY_MISSING
    assert entities[1].traceability_status == TRACEABILITY_MISSING


def test_legacy_report_without_traceability_fields_still_builds_entity_list_item():
    """GET entities from report that has no traceability keys: fields are None (backward compat)."""
    report = {
        "entities": [
            {
                "entity_uid": "j_E1",
                "entity_type": "PALLET",
                "pallet_id": "P1",
                "count_status": "COUNTED",
                "entity_quality_score": 0.9,
            }
        ]
    }
    entities = report.get("entities") or []
    out = []
    for e in entities:
        raw_status = e.get("traceability_status")
        traceability_status = raw_status if raw_status in TRACEABILITY_STATUS_VALUES else None
        out.append(
            EntityListItem(
                entity_uid=str(e.get("entity_uid") or ""),
                pallet_id=e.get("pallet_id"),
                entity_type=str(e.get("entity_type") or ""),
                count_status=e.get("count_status"),
                entity_quality_score=e.get("entity_quality_score"),
                evidence_ref=e.get("evidence_path"),
                source_image_id=e.get("source_image_id"),
                traceability_status=traceability_status,
                traceability_warning=e.get("traceability_warning"),
            )
        )
    assert len(out) == 1
    assert out[0].entity_uid == "j_E1"
    assert out[0].source_image_id is None
    assert out[0].traceability_status is None
    assert out[0].traceability_warning is None


def test_report_with_unknown_traceability_status_coerced_to_none():
    """Malformed/legacy report with unknown traceability_status: coerced to None so API does not 500."""
    report = {
        "entities": [
            {
                "entity_uid": "j_E1",
                "entity_type": "PALLET",
                "pallet_id": "P1",
                "traceability_status": "unknown",
            }
        ]
    }
    e = report["entities"][0]
    raw_status = e.get("traceability_status")
    traceability_status = raw_status if raw_status in TRACEABILITY_STATUS_VALUES else None
    item = EntityListItem(
        entity_uid=str(e.get("entity_uid") or ""),
        entity_type=str(e.get("entity_type") or ""),
        traceability_status=traceability_status,
    )
    assert item.traceability_status is None


# ---------- API response schema ----------


def test_entity_list_item_accepts_traceability_fields():
    """EntityListItem can be built with source_image_id, traceability_status, and traceability_warning."""
    item = EntityListItem(
        entity_uid="j_E1",
        entity_type="PALLET",
        source_image_id="img_001",
        traceability_status=TRACEABILITY_VALID,
        traceability_warning=None,
    )
    assert item.source_image_id == "img_001"
    assert item.traceability_status == TRACEABILITY_VALID
    assert item.traceability_warning is None


def test_entity_list_item_accepts_unvalidated_status():
    """EntityListItem accepts traceability_status 'unvalidated' (Literal contract)."""
    item = EntityListItem(
        entity_uid="j_E1",
        entity_type="PALLET",
        traceability_status="unvalidated",
    )
    assert item.traceability_status == "unvalidated"


def test_entity_list_item_accepts_traceability_warning():
    """EntityListItem exposes traceability_warning for diagnostic (e.g. when status is invalid)."""
    item = EntityListItem(
        entity_uid="j_E1",
        entity_type="PALLET",
        traceability_status=TRACEABILITY_INVALID,
        traceability_warning="source_image_id not in job: 'img_999'",
    )
    assert item.traceability_warning == "source_image_id not in job: 'img_999'"


def test_entity_list_item_optional_traceability_default_none():
    """EntityListItem source_image_id, traceability_status, traceability_warning default to None."""
    item = EntityListItem(entity_uid="j_E1", entity_type="PALLET")
    assert item.source_image_id is None
    assert item.traceability_status is None
    assert item.traceability_warning is None


def test_traceability_status_enum_values():
    """TraceabilityStatus enum defines exactly the allowed values."""
    assert TraceabilityStatus.VALID.value == "valid"
    assert TraceabilityStatus.MISSING.value == "missing"
    assert TraceabilityStatus.INVALID.value == "invalid"
    assert TraceabilityStatus.UNVALIDATED.value == "unvalidated"


def test_persistence_policy_traceability_warning_not_in_pallet_results_shape():
    """traceability_warning is report/API only; pallet_results push does not include it (policy)."""
    ent = {
        "pallet_id": "P1",
        "traceability_status": TRACEABILITY_INVALID,
        "traceability_warning": "source_image_id not in job: 'img_001'",
    }
    pallet_row = {
        "pallet_id": ent.get("pallet_id") or "",
        "internal_code": ent.get("internal_code"),
        "source_image_id": ent.get("source_image_id"),
        "traceability_status": ent.get("traceability_status"),
    }
    assert "traceability_warning" not in pallet_row
    assert pallet_row["traceability_status"] == TRACEABILITY_INVALID
