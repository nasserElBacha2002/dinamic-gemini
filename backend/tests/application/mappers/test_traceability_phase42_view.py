"""Phase 4.2 — canonical view / API traceability block exposes has_valid_evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.mappers.position_canonical_view import build_position_canonical_view
from src.domain.positions.entities import Position, PositionStatus


def test_invalid_traceability_has_valid_evidence_false() -> None:
    now = datetime.now(timezone.utc)
    position = Position(
        id="pos-inv",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "source_image_id": "asset-dropped",
            "traceability_status": "invalid",
            "traceability_warning": "Returned image ID was not part of the final provider payload.",
            "has_valid_evidence": False,
            "internal_code": "SKU-1",
            "final_quantity": 1,
        },
        job_id="job-1",
    )
    view = build_position_canonical_view(position)
    assert view.traceability.traceability_status == "invalid"
    assert view.traceability.source_image_id == "asset-dropped"
    assert view.traceability.has_valid_evidence is False
    assert view.traceability.traceability_warning is not None
    assert view.review.has_evidence is True


def test_valid_traceability_has_valid_evidence_true() -> None:
    now = datetime.now(timezone.utc)
    position = Position(
        id="pos-ok",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.95,
        needs_review=False,
        primary_evidence_id="ev-2",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "source_image_id": "asset-1",
            "traceability_status": "valid",
            "has_valid_evidence": True,
            "internal_code": "SKU-2",
            "final_quantity": 2,
        },
        job_id="job-1",
    )
    view = build_position_canonical_view(position)
    assert view.traceability.traceability_status == "valid"
    assert view.traceability.has_valid_evidence is True


def test_persisted_false_with_valid_status_has_valid_evidence_false() -> None:
    now = datetime.now(timezone.utc)
    position = Position(
        id="pos-contradiction",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "source_image_id": "asset-1",
            "traceability_status": "valid",
            "has_valid_evidence": False,
            "internal_code": "SKU-X",
            "final_quantity": 1,
        },
        job_id="job-1",
    )
    view = build_position_canonical_view(position)
    assert view.traceability.has_valid_evidence is False


def test_persisted_absent_with_valid_status_has_valid_evidence_false() -> None:
    now = datetime.now(timezone.utc)
    position = Position(
        id="pos-legacy",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-2",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "source_image_id": "asset-1",
            "traceability_status": "valid",
            "internal_code": "SKU-Y",
            "final_quantity": 1,
        },
        job_id="job-1",
    )
    view = build_position_canonical_view(position)
    assert view.traceability.has_valid_evidence is False


def test_persisted_true_with_invalid_status_has_valid_evidence_false() -> None:
    now = datetime.now(timezone.utc)
    position = Position(
        id="pos-stale-true",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id="ev-3",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "source_image_id": "asset-1",
            "traceability_status": "invalid",
            "has_valid_evidence": True,
            "internal_code": "SKU-Z",
            "final_quantity": 1,
        },
        job_id="job-1",
    )
    view = build_position_canonical_view(position)
    assert view.traceability.has_valid_evidence is False


def test_persisted_true_with_valid_status_empty_source_has_valid_evidence_false() -> None:
    now = datetime.now(timezone.utc)
    position = Position(
        id="pos-no-source",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id="ev-4",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "source_image_id": "",
            "traceability_status": "valid",
            "has_valid_evidence": True,
            "internal_code": "SKU-W",
            "final_quantity": 1,
        },
        job_id="job-1",
    )
    view = build_position_canonical_view(position)
    assert view.traceability.has_valid_evidence is False
