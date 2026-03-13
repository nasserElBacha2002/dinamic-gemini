"""Tests for v3 report mapper and PersistAisleResult use case — Épica 6."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.domain.evidence.entities import Evidence
from src.domain.positions.entities import PositionStatus
from src.infrastructure.pipeline.v3_report_mapper import (
    MappedAisleResult,
    map_hybrid_report_to_domain,
)


def test_map_hybrid_report_to_domain_empty_entities():
    """Empty entities list produces no positions/products/evidences."""
    report = {"entities": []}
    now = datetime.now(timezone.utc)
    result = map_hybrid_report_to_domain(
        aisle_id="aisle-1",
        report=report,
        run_dir=Path("/out/job1/run"),
        run_id="run",
        job_id="job1",
        now=now,
    )
    assert isinstance(result, MappedAisleResult)
    assert result.positions == []
    assert result.product_records == []
    assert result.evidences == []


def test_map_hybrid_report_to_domain_one_entity():
    """One report entity produces one position, one product, one evidence."""
    report = {
        "entities": [
            {
                "entity_uid": "e1",
                "entity_type": "pallet",
                "pallet_id": "P1",
                "internal_code": "SKU-001",
                "final_quantity": 5,
                "product_label_quantity": 5,
                "confidence": 0.92,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop_0.jpg",
            }
        ]
    }
    now = datetime.now(timezone.utc)
    result = map_hybrid_report_to_domain(
        aisle_id="aisle-1",
        report=report,
        run_dir=Path("/out/job1/run"),
        run_id="run",
        job_id="job1",
        now=now,
    )
    assert len(result.positions) == 1
    assert len(result.product_records) == 1
    assert len(result.evidences) == 1

    pos = result.positions[0]
    assert pos.aisle_id == "aisle-1"
    assert pos.status == PositionStatus.DETECTED
    assert pos.confidence == 0.92
    assert pos.needs_review is False
    assert pos.primary_evidence_id == result.evidences[0].id
    assert pos.detected_summary_json is not None
    assert pos.detected_summary_json.get("internal_code") == "SKU-001"

    pr = result.product_records[0]
    assert pr.position_id == pos.id
    assert pr.sku == "SKU-001"
    assert pr.detected_quantity == 5

    ev = result.evidences[0]
    assert ev.entity_type == "position"
    assert ev.entity_id == pos.id
    assert "job1/run/evidence/crop_0.jpg" in ev.storage_path
    assert ev.is_primary is True
    assert ev.source_asset_id is None


def test_map_hybrid_report_needs_review():
    """count_status NEEDS_REVIEW sets needs_review=True; missing evidence_path uses no_artifact."""
    report = {
        "entities": [
            {
                "entity_uid": "e2",
                "internal_code": "X",
                "final_quantity": 0,
                "confidence": 0.5,
                "count_status": "NEEDS_REVIEW",
            }
        ]
    }
    now = datetime.now(timezone.utc)
    result = map_hybrid_report_to_domain(
        aisle_id="a",
        report=report,
        run_dir=Path("/run"),
        run_id="run",
        job_id="j",
        now=now,
    )
    assert len(result.positions) == 1
    assert result.positions[0].needs_review is True
    assert result.evidences[0].storage_path == "no_artifact"
    assert result.evidences[0].source_asset_id is None


def test_map_hybrid_report_stores_position_barcode_and_review_display_label_for_sku_fallback():
    """detected_summary_json includes position_barcode and review_display_label when present (list API sku fallback)."""
    report = {
        "entities": [
            {
                "entity_uid": "e3",
                "internal_code": None,
                "position_barcode": "PALLET-99",
                "review_display_label": "Pallet PALLET-99",
                "final_quantity": None,
                "product_label_quantity": 1,
                "confidence": 0.6,
                "count_status": "NEEDS_REVIEW",
            }
        ]
    }
    now = datetime.now(timezone.utc)
    result = map_hybrid_report_to_domain(
        aisle_id="a",
        report=report,
        run_dir=Path("/run"),
        run_id="run",
        job_id="j",
        now=now,
    )
    assert len(result.positions) == 1
    summary = result.positions[0].detected_summary_json
    assert summary is not None
    assert summary.get("position_barcode") == "PALLET-99"
    assert summary.get("review_display_label") == "Pallet PALLET-99"
    assert summary.get("internal_code") is None
    """PersistAisleResultUseCase saves positions, products, evidences."""
    position_repo = MagicMock()
    product_repo = MagicMock()
    evidence_repo = MagicMock()
    clock = MagicMock()
    now = datetime.now(timezone.utc)
    clock.now.return_value = now

    use_case = PersistAisleResultUseCase(
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        clock=clock,
    )
    report = {
        "entities": [
            {
                "entity_uid": "e1",
                "internal_code": "SKU-A",
                "final_quantity": 3,
                "confidence": 0.88,
                "count_status": "COUNTED",
            }
        ]
    }
    use_case.execute(
        PersistAisleResultCommand(
            aisle_id="aisle-1",
            job_id="job-1",
            report=report,
            run_dir=Path("/out/job-1/run"),
            run_id="run",
        )
    )
    assert position_repo.save.call_count == 1
    assert product_repo.save.call_count == 1
    assert evidence_repo.save.call_count == 1
