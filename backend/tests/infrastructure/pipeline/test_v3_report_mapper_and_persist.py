"""Tests for v3 report mapper and PersistAisleResult use case — Épica 6."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.dto.mapped_aisle_result import MappedAisleResult
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
    should_persist_detected_position,
)
from tests.support.worker_phase2.persist_builders import build_persist_aisle_result_use_case
from src.domain.positions.entities import PositionStatus
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
from src.infrastructure.pipeline.v3_report_mapper import map_hybrid_report_to_domain


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
    assert result.raw_labels == []


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
    assert len(result.raw_labels) == 1
    assert result.raw_labels[0].sku_raw == "SKU-001"
    assert result.raw_labels[0].aisle_id == "aisle-1"

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
    assert pr.qty_source in ("detected", "consolidated", "label_explicit")
    assert pr.qty_inference_reason is None
    assert pr.qty_parse_status is not None

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


def test_map_hybrid_report_openai_style_needs_review_uses_product_label_quantity_when_final_null():
    """Multi-provider: hybrid report has final_quantity=null but model quantity on product_label_quantity.

    Mirrors PALLET + NEEDS_REVIEW when label qty exists without position barcode (count_status
    clears final_quantity). Mapper must not treat null final_quantity as the only quantity field.
    """
    report = {
        "entities": [
            {
                "entity_uid": "e-openai-nr",
                "entity_type": "PALLET",
                "model_entity_id": "entity_1",
                "internal_code": None,
                "position_barcode": None,
                "product_label_quantity": 12,
                "product_label_bbox": [0.077, 0.517, 0.813, 0.793],
                "final_quantity": None,
                "confidence": 0.97,
                "count_status": "NEEDS_REVIEW",
                "evidence_path": "evidence/crop.jpg",
                "has_boxes": True,
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
    pr = result.product_records[0]
    assert pr.detected_quantity == 12
    assert pr.qty_source == "label_explicit"
    assert pr.qty_inference_reason is None
    assert pr.qty_parse_status == "valid_positive"
    summary = result.positions[0].detected_summary_json or {}
    assert summary.get("qty_final") == 12
    assert summary.get("qty_origin_field") == "product_label_quantity"
    assert result.positions[0].needs_review is True
    assert pr.sku == "UNKNOWN"


def test_map_hybrid_report_infers_min_qty_when_counted_has_evidence_but_missing_qty():
    """v3.2.2: COUNTED + evidence but no explicit qty -> qty_final=1 inferred."""
    report = {
        "entities": [
            {
                "entity_uid": "e-inf-1",
                "entity_type": "PALLET",
                "internal_code": "SKU-X",
                "final_quantity": None,
                "product_label_quantity": None,
                "confidence": 0.9,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop.jpg",
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
    assert len(result.product_records) == 1
    pr = result.product_records[0]
    assert pr.detected_quantity == 1
    assert pr.qty_source == "inferred"
    assert pr.qty_inference_reason == "valid_evidence_without_explicit_quantity"
    summary = result.positions[0].detected_summary_json or {}
    assert summary.get("qty_final") == 1
    assert summary.get("qty_source") == "inferred"
    assert summary.get("qty_inference_reason") == "valid_evidence_without_explicit_quantity"


def test_map_hybrid_report_persists_unresolved_when_insufficient_evidence():
    """v3.2.2: No evidence_path + no explicit qty -> qty_source=unresolved, is_resolved False, so API can treat as non-valid visible."""
    report = {
        "entities": [
            {
                "entity_uid": "e-unr",
                "entity_type": "PALLET",
                "internal_code": "SKU-Y",
                "final_quantity": None,
                "product_label_quantity": None,
                "confidence": 0.5,
                "count_status": "COUNTED",
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
    assert len(result.product_records) == 1
    pr = result.product_records[0]
    assert pr.qty_source == "unresolved"
    assert pr.detected_quantity == 0
    summary = result.positions[0].detected_summary_json or {}
    assert summary.get("qty_source") == "unresolved"
    assert summary.get("qty_is_resolved") is False


def test_map_hybrid_report_needs_review_with_strong_presence_infers_one():
    """NEEDS_REVIEW + valid evidence + valid traceability + identity -> qty_final=1 inferred."""
    report = {
        "entities": [
            {
                "entity_uid": "e-nr-strong",
                "entity_type": "PALLET",
                "internal_code": "SKU-STRONG",
                "final_quantity": None,
                "product_label_quantity": None,
                "confidence": 0.9,
                "count_status": "NEEDS_REVIEW",
                "evidence_path": "evidence/crop.jpg",
                "traceability_status": "valid",
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
    assert len(result.product_records) == 1
    pr = result.product_records[0]
    assert pr.detected_quantity == 1
    assert pr.qty_source == "inferred"
    assert pr.qty_inference_reason == "valid_evidence_without_explicit_quantity"
    summary = result.positions[0].detected_summary_json or {}
    assert summary.get("qty_final") == 1
    assert summary.get("qty_source") == "inferred"
    assert summary.get("qty_inference_reason") == "valid_evidence_without_explicit_quantity"


def test_map_hybrid_report_needs_review_with_weak_presence_stays_unresolved():
    """NEEDS_REVIEW but weak evidence/identity does not trigger inference."""
    report = {
        "entities": [
            {
                "entity_uid": "e-nr-weak",
                "entity_type": "PALLET",
                "internal_code": None,
                "final_quantity": None,
                "product_label_quantity": None,
                "confidence": 0.6,
                "count_status": "NEEDS_REVIEW",
                # No evidence_path, no identity, traceability missing/invalid.
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
    assert len(result.product_records) == 1
    pr = result.product_records[0]
    assert pr.detected_quantity == 0
    assert pr.qty_source == "unresolved"
    summary = result.positions[0].detected_summary_json or {}
    assert summary.get("qty_source") == "unresolved"
    assert summary.get("qty_is_resolved") is False


def test_map_hybrid_report_empty_pallet_explicit_zero_preserved():
    """v3.2.2: EMPTY_PALLET with explicit zero -> qty_final=0, is_resolved True (allowed domain case)."""
    report = {
        "entities": [
            {
                "entity_uid": "e-empty",
                "entity_type": "EMPTY_PALLET",
                "internal_code": None,
                "final_quantity": 0,
                "product_label_quantity": 0,
                "confidence": 0.9,
                "count_status": "EMPTY",
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
    assert len(result.product_records) == 1
    pr = result.product_records[0]
    assert pr.detected_quantity == 0
    assert pr.qty_source == "detected"
    summary = result.positions[0].detected_summary_json or {}
    assert summary.get("qty_final") == 0
    assert summary.get("qty_is_resolved") is True


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


def _mock_bundle_repo(repo: MagicMock) -> MagicMock:
    repo._store = {}
    repo.list_by_aisle.return_value = []
    repo.list_for_scope.return_value = []
    repo.list_by_position.return_value = []
    repo.list_by_entity.return_value = []
    return repo


def test_persist_aisle_result_use_case_saves_positions_products_evidences() -> None:
    """PersistAisleResultUseCase saves positions, products, evidences."""
    position_repo = _mock_bundle_repo(MagicMock())
    product_repo = _mock_bundle_repo(MagicMock())
    evidence_repo = _mock_bundle_repo(MagicMock())
    raw_repo = _mock_bundle_repo(MagicMock())
    norm_repo = _mock_bundle_repo(MagicMock())
    final_repo = _mock_bundle_repo(MagicMock())
    aisle_repo = MagicMock()
    mock_aisle = MagicMock()
    mock_aisle.inventory_id = "inv-persist-test"
    aisle_repo.get_by_id.return_value = mock_aisle
    clock = MagicMock()
    now = datetime.now(timezone.utc)
    clock.now.return_value = now

    use_case = build_persist_aisle_result_use_case(
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        aisle_repo=aisle_repo,
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
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


@pytest.mark.parametrize(
    ("sku", "qty", "expected"),
    [
        ("UNKNOWN", 0, False),
        ("", 0, False),
        (None, 0, False),
        ("UNKNOWN", None, False),
        ("1242879", 0, True),
        ("UNKNOWN", 3, True),
        (None, 5, True),
    ],
)
def test_should_persist_detected_position_business_rule(sku, qty, expected):
    assert should_persist_detected_position(sku, qty) is expected


@pytest.mark.parametrize(
    ("internal_code", "final_quantity", "expected_saves"),
    [
        ("UNKNOWN", 0, 0),
        ("", 0, 0),
        (None, 0, 0),
        ("UNKNOWN", None, 0),
        ("1242879", 0, 1),
        ("UNKNOWN", 3, 1),
        (None, 5, 1),
    ],
)
def test_persist_aisle_result_use_case_applies_unknown_zero_filter(
    internal_code, final_quantity, expected_saves
) -> None:
    position_repo = _mock_bundle_repo(MagicMock())
    product_repo = _mock_bundle_repo(MagicMock())
    evidence_repo = _mock_bundle_repo(MagicMock())
    raw_repo = _mock_bundle_repo(MagicMock())
    norm_repo = _mock_bundle_repo(MagicMock())
    final_repo = _mock_bundle_repo(MagicMock())
    aisle_repo = MagicMock()
    mock_aisle = MagicMock()
    mock_aisle.inventory_id = "inv-persist-test"
    aisle_repo.get_by_id.return_value = mock_aisle
    clock = MagicMock()
    now = datetime.now(timezone.utc)
    clock.now.return_value = now

    use_case = build_persist_aisle_result_use_case(
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        aisle_repo=aisle_repo,
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        clock=clock,
    )
    report = {
        "entities": [
            {
                "entity_uid": "e-filter",
                "internal_code": internal_code,
                "final_quantity": final_quantity,
                "confidence": 0.9,
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

    assert position_repo.save.call_count == expected_saves
    assert product_repo.save.call_count == expected_saves
    assert evidence_repo.save.call_count == expected_saves


def test_persist_aisle_result_raises_on_mapped_length_mismatch() -> None:
    position_repo = MagicMock()
    product_repo = MagicMock()
    evidence_repo = MagicMock()
    aisle_repo = MagicMock()
    mock_aisle = MagicMock()
    mock_aisle.inventory_id = "inv-persist-test"
    aisle_repo.get_by_id.return_value = mock_aisle
    clock = MagicMock()
    now = datetime.now(timezone.utc)
    clock.now.return_value = now

    mapped = map_hybrid_report_to_domain(
        aisle_id="aisle-1",
        report={
            "entities": [
                {
                    "entity_uid": "e-mismatch",
                    "internal_code": "SKU-A",
                    "final_quantity": 1,
                    "confidence": 0.9,
                    "count_status": "COUNTED",
                }
            ]
        },
        run_dir=Path("/out/job-1/run"),
        run_id="run",
        job_id="job-1",
        now=now,
    )
    mapped.evidences = []

    def _fake_mapper(**_kwargs: object) -> MappedAisleResult:
        return mapped

    raw_repo = _mock_bundle_repo(MagicMock())
    norm_repo = _mock_bundle_repo(MagicMock())
    final_repo = _mock_bundle_repo(MagicMock())
    position_repo = _mock_bundle_repo(position_repo)
    product_repo = _mock_bundle_repo(product_repo)
    evidence_repo = _mock_bundle_repo(evidence_repo)

    use_case = build_persist_aisle_result_use_case(
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        aisle_repo=aisle_repo,
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        clock=clock,
        hybrid_mapper=_fake_mapper,
    )

    with pytest.raises(
        ValueError,
        match="PersistAisleResult invariant broken: positions=1 product_records=1 evidences=0",
    ):
        use_case.execute(
            PersistAisleResultCommand(
                aisle_id="aisle-1",
                job_id="job-1",
                report={"entities": []},
                run_dir=Path("/out/job-1/run"),
                run_id="run",
            )
        )
