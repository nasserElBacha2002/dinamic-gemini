"""Epic 3.1.C — Backend traceability review/audit: summary, export, filter.

Tests: traceability_summary computation, report/CSV enrichment, list_entities
traceability_summary semantics (full-job only), typed TraceabilitySummary,
traceability_status filter validation (422 for invalid), backward compatibility.
"""

import tempfile
from pathlib import Path

from src.domain.entity import Entity
from src.domain.traceability import (
    TraceabilityStatus,
    compute_traceability_summary,
    compute_traceability_summary_from_entity_dicts,
)
from src.reporting.artifacts import write_report_csv
from src.reporting.hybrid_report import build_hybrid_report

# ---------- compute_traceability_summary ----------


def test_compute_traceability_summary_counts_by_status():
    """Summary counts valid, missing, invalid, unvalidated and total_entities."""
    entities = [
        Entity("u1", "PALLET", "m1", traceability_status=TraceabilityStatus.VALID.value),
        Entity("u2", "PALLET", "m2", traceability_status=TraceabilityStatus.MISSING.value),
        Entity("u3", "PALLET", "m3", traceability_status=TraceabilityStatus.INVALID.value),
        Entity("u4", "PALLET", "m4", traceability_status=TraceabilityStatus.UNVALIDATED.value),
        Entity("u5", "PALLET", "m5", traceability_status=TraceabilityStatus.VALID.value),
    ]
    summary = compute_traceability_summary(entities)
    assert summary["total_entities"] == 5
    assert summary["valid"] == 2
    assert summary["missing"] == 1
    assert summary["invalid"] == 1
    assert summary["unvalidated"] == 1


def test_compute_traceability_summary_empty_list():
    """Empty entity list returns zero counts."""
    summary = compute_traceability_summary([])
    assert summary["total_entities"] == 0
    assert summary["valid"] == 0
    assert summary["missing"] == 0
    assert summary["invalid"] == 0
    assert summary["unvalidated"] == 0


def test_compute_traceability_summary_legacy_entities_without_status_counted_as_missing():
    """Entities without traceability_status are counted as missing (documented policy)."""
    entities = [
        Entity("u1", "PALLET", "m1"),  # no traceability_status
        Entity("u2", "PALLET", "m2", traceability_status=TraceabilityStatus.VALID.value),
    ]
    summary = compute_traceability_summary(entities)
    assert summary["total_entities"] == 2
    assert summary["missing"] == 1
    assert summary["valid"] == 1


# ---------- compute_traceability_summary_from_entity_dicts ----------


def test_compute_traceability_summary_from_entity_dicts_matches_entity_version():
    """from_entity_dicts produces same counts as compute_traceability_summary for same data."""
    entities = [
        Entity("u1", "PALLET", "m1", traceability_status=TraceabilityStatus.VALID.value),
        Entity("u2", "PALLET", "m2", traceability_status=TraceabilityStatus.MISSING.value),
        Entity("u3", "PALLET", "m3", traceability_status=TraceabilityStatus.INVALID.value),
    ]
    dicts = [
        {"entity_uid": "u1", "traceability_status": "valid"},
        {"entity_uid": "u2", "traceability_status": "missing"},
        {"entity_uid": "u3", "traceability_status": "invalid"},
    ]
    from_entities = compute_traceability_summary(entities)
    from_dicts = compute_traceability_summary_from_entity_dicts(dicts)
    assert from_entities["total_entities"] == from_dicts["total_entities"] == 3
    assert from_entities["valid"] == from_dicts["valid"] == 1
    assert from_entities["missing"] == from_dicts["missing"] == 1
    assert from_entities["invalid"] == from_dicts["invalid"] == 1


def test_compute_traceability_summary_from_entity_dicts_legacy_unknown_as_missing():
    """Dicts without traceability_status or with unknown value are counted as missing."""
    dicts = [
        {"entity_uid": "e1"},
        {"entity_uid": "e2", "traceability_status": "unknown"},
        {"entity_uid": "e3", "traceability_status": "valid"},
    ]
    summary = compute_traceability_summary_from_entity_dicts(dicts)
    assert summary["total_entities"] == 3
    assert summary["missing"] == 2
    assert summary["valid"] == 1


# ---------- Report traceability_summary ----------


def test_build_hybrid_report_includes_traceability_summary():
    """Report dict includes traceability_summary block with counts."""
    entities = [
        Entity("u1", "PALLET", "m1", traceability_status=TraceabilityStatus.VALID.value),
        Entity("u2", "PALLET", "m2", traceability_status=TraceabilityStatus.MISSING.value),
    ]
    report = build_hybrid_report(
        video_path="/tmp/v.mp4",
        entities=entities,
        frames_selected=5,
    )
    assert "traceability_summary" in report
    ts = report["traceability_summary"]
    assert ts["total_entities"] == 2
    assert ts["valid"] == 1
    assert ts["missing"] == 1
    assert ts["invalid"] == 0
    assert ts["unvalidated"] == 0


def test_build_hybrid_report_backward_compat_entities_without_traceability():
    """Report builds and traceability_summary treats entities without status as missing."""
    entities = [
        Entity("u1", "PALLET", "m1"),  # legacy: no traceability fields
    ]
    report = build_hybrid_report(
        video_path="/tmp/v.mp4",
        entities=entities,
        frames_selected=5,
    )
    assert "traceability_summary" in report
    assert report["traceability_summary"]["total_entities"] == 1
    assert report["traceability_summary"]["missing"] == 1
    assert "entities" in report
    assert len(report["entities"]) == 1
    assert report["entities"][0].get("source_image_id") is None


# ---------- write_report_csv ----------


def test_write_report_csv_includes_traceability_columns():
    """CSV has header and rows with source_image_id, traceability_status, traceability_warning."""
    report = {
        "entities": [
            {
                "entity_uid": "e1",
                "pallet_id": "P01",
                "entity_type": "PALLET",
                "count_status": "COUNTED",
                "final_quantity": 10,
                "internal_code": "SKU1",
                "confidence": 0.9,
                "source_image_id": "img_001",
                "traceability_status": "valid",
                "traceability_warning": None,
            },
            {
                "entity_uid": "e2",
                "pallet_id": "P02",
                "entity_type": "PALLET",
                "count_status": "NEEDS_REVIEW",
                "final_quantity": None,
                "internal_code": "SKU2",
                "confidence": 0.7,
                "source_image_id": None,
                "traceability_status": "missing",
                "traceability_warning": None,
            },
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.csv"
        write_report_csv(path, report)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "source_image_id" in content
        assert "traceability_status" in content
        assert "traceability_warning" in content
        assert "img_001" in content
        assert "valid" in content
        assert "missing" in content


def test_write_report_csv_empty_entities_writes_header_only():
    """Empty entities list writes header row only."""
    report = {"entities": []}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.csv"
        write_report_csv(path, report)
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert "traceability_status" in lines[0]


def test_write_report_csv_backward_compat_no_traceability_fields():
    """Entities without traceability fields get empty cells (backward compat)."""
    report = {
        "entities": [
            {
                "entity_uid": "e1",
                "pallet_id": "P01",
                "entity_type": "PALLET",
                "count_status": "COUNTED",
                "final_quantity": 5,
                "internal_code": "X",
                "confidence": 0.8,
            },
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.csv"
        write_report_csv(path, report)
        content = path.read_text(encoding="utf-8")
        assert "e1" in content
        assert "P01" in content
        lines = content.strip().splitlines()
    assert len(lines) == 2  # header + 1 row


# ---------- list_entities API: v1 routes removed in Stage 3; traceability in v3 positions ---
