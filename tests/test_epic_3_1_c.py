"""Epic 3.1.C — Backend traceability review/audit: summary, export, filter.

Tests: traceability_summary computation, report/CSV enrichment, list_entities
traceability_summary semantics (full-job only), typed TraceabilitySummary,
traceability_status filter validation (422 for invalid), backward compatibility.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.domain.entity import Entity
from src.domain.traceability import (
    TraceabilityStatus,
    compute_traceability_summary,
    compute_traceability_summary_from_entity_dicts,
)
from src.jobs.job_store import create_job, update_job
from src.jobs.models import JobOutput, JobStatus
from src.reporting.hybrid_report import build_hybrid_report
from src.reporting.artifacts import write_report_csv


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


# ---------- list_entities API: traceability_summary semantics + filter ----------


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def job_with_traceability_report(tmp_path):
    """Job with hybrid_report.json containing traceability_summary and entity traceability_status."""
    job_id = "job_epic31c_test"
    run_dir = tmp_path / job_id / "run"
    run_dir.mkdir(parents=True)
    report = {
        "report_version": "2.1",
        "mode": "hybrid_v2.1",
        "summary": {"total_entities": 3, "pallets": 3, "counted": 1, "needs_review": 2, "counted_manual": 0},
        "traceability_summary": {
            "total_entities": 3,
            "valid": 1,
            "missing": 1,
            "invalid": 1,
            "unvalidated": 0,
        },
        "entities": [
            {"entity_uid": "E1", "pallet_id": "P1", "entity_type": "PALLET", "count_status": "COUNTED", "traceability_status": "valid"},
            {"entity_uid": "E2", "pallet_id": "P2", "entity_type": "PALLET", "count_status": "NEEDS_REVIEW", "traceability_status": "missing"},
            {"entity_uid": "E3", "pallet_id": "P3", "entity_type": "PALLET", "count_status": "NEEDS_REVIEW", "traceability_status": "invalid"},
        ],
    }
    report_path = run_dir / "hybrid_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    create_job(tmp_path, job_id, video_path=str(tmp_path / "v.mp4"), mode="hybrid", confidence_threshold=0.7)
    update_job(tmp_path, job_id, status=JobStatus.SUCCEEDED, output=JobOutput(report_json_path=str(report_path)))
    return job_id, tmp_path, report_path, run_dir


def test_list_entities_traceability_summary_always_full_job(client, job_with_traceability_report):
    """traceability_summary in response is always full-job counts, not filtered subset."""
    job_id, tmp_path, report_path, run_dir = job_with_traceability_report
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities")
    assert r.status_code == 200
    data = r.json()
    assert "traceability_summary" in data
    ts = data["traceability_summary"]
    assert ts["total_entities"] == 3
    assert ts["valid"] == 1
    assert ts["missing"] == 1
    assert ts["invalid"] == 1
    assert ts["unvalidated"] == 0
    assert len(data["entities"]) == 3

    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r2 = client.get(f"/api/v1/inventory/jobs/{job_id}/entities?traceability_status=valid")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["entities"]) == 1
    assert data2["entities"][0]["entity_uid"] == "E1"
    assert data2["traceability_summary"]["total_entities"] == 3
    assert data2["traceability_summary"]["valid"] == 1
    assert data2["traceability_summary"]["missing"] == 1
    assert data2["traceability_summary"]["invalid"] == 1


def test_list_entities_traceability_summary_typed_contract(client, job_with_traceability_report):
    """When traceability_summary is present, response has all required typed fields."""
    job_id, tmp_path, report_path, run_dir = job_with_traceability_report
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities")
    assert r.status_code == 200
    ts = r.json().get("traceability_summary")
    assert ts is not None
    for key in ("total_entities", "valid", "missing", "invalid", "unvalidated"):
        assert key in ts
        assert isinstance(ts[key], int)


def test_list_entities_invalid_traceability_status_returns_422(client, job_with_traceability_report):
    """Invalid traceability_status query value returns 422 with allowed values in detail."""
    job_id, tmp_path, report_path, run_dir = job_with_traceability_report
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities?traceability_status=invalid_value")
    assert r.status_code == 422
    detail = r.json().get("detail", "")
    assert "traceability_status" in detail or "one of" in detail.lower()


def test_list_entities_valid_traceability_filter(client, job_with_traceability_report):
    """Valid traceability_status filter returns only matching entities."""
    job_id, tmp_path, report_path, run_dir = job_with_traceability_report
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities?traceability_status=missing")
    assert r.status_code == 200
    data = r.json()
    assert len(data["entities"]) == 1
    assert data["entities"][0]["traceability_status"] == "missing"
    assert data["traceability_summary"]["total_entities"] == 3


def test_list_entities_backward_compat_no_traceability_summary(client, tmp_path):
    """Legacy report without traceability_summary: summary computed from full entity list and returned as typed."""
    job_id = "job_legacy_no_ts"
    run_dir = tmp_path / job_id / "run"
    run_dir.mkdir(parents=True)
    report = {
        "report_version": "2.1",
        "mode": "hybrid_v2.1",
        "summary": {"total_entities": 2},
        "entities": [
            {"entity_uid": "E1", "entity_type": "PALLET", "traceability_status": "valid"},
            {"entity_uid": "E2", "entity_type": "PALLET"},
        ],
    }
    report_path = run_dir / "hybrid_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    create_job(tmp_path, job_id, video_path=str(tmp_path / "v.mp4"), mode="hybrid", confidence_threshold=0.7)
    update_job(tmp_path, job_id, status=JobStatus.SUCCEEDED, output=JobOutput(report_json_path=str(report_path)))
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities")
    assert r.status_code == 200
    data = r.json()
    assert data["traceability_summary"] is not None
    assert data["traceability_summary"]["total_entities"] == 2
    assert data["traceability_summary"]["valid"] == 1
    assert data["traceability_summary"]["missing"] == 1


def test_list_entities_malformed_traceability_summary_fallback(client, tmp_path):
    """Report with malformed traceability_summary returns 200 and summary is recomputed from full entity list."""
    job_id = "job_malformed_ts"
    run_dir = tmp_path / job_id / "run"
    run_dir.mkdir(parents=True)
    report = {
        "report_version": "2.1",
        "mode": "hybrid_v2.1",
        "summary": {"total_entities": 2},
        "traceability_summary": {"valid": 1, "missing": 1},
        "entities": [
            {"entity_uid": "E1", "entity_type": "PALLET", "traceability_status": "valid"},
            {"entity_uid": "E2", "entity_type": "PALLET", "traceability_status": "missing"},
        ],
    }
    report_path = run_dir / "hybrid_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    create_job(tmp_path, job_id, video_path=str(tmp_path / "v.mp4"), mode="hybrid", confidence_threshold=0.7)
    update_job(tmp_path, job_id, status=JobStatus.SUCCEEDED, output=JobOutput(report_json_path=str(report_path)))
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities")
    assert r.status_code == 200
    data = r.json()
    assert data["traceability_summary"] is not None
    assert data["traceability_summary"]["total_entities"] == 2
    assert data["traceability_summary"]["valid"] == 1
    assert data["traceability_summary"]["missing"] == 1


def test_list_entities_traceability_status_normalized(client, tmp_path):
    """Entity traceability_status from report is normalized to lowercase in response (e.g. Valid -> valid)."""
    job_id = "job_normalized_ts"
    run_dir = tmp_path / job_id / "run"
    run_dir.mkdir(parents=True)
    report = {
        "report_version": "2.1",
        "mode": "hybrid_v2.1",
        "summary": {"total_entities": 1},
        "traceability_summary": {"total_entities": 1, "valid": 1, "missing": 0, "invalid": 0, "unvalidated": 0},
        "entities": [
            {"entity_uid": "E1", "entity_type": "PALLET", "traceability_status": "Valid"},
        ],
    }
    report_path = run_dir / "hybrid_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    create_job(tmp_path, job_id, video_path=str(tmp_path / "v.mp4"), mode="hybrid", confidence_threshold=0.7)
    update_job(tmp_path, job_id, status=JobStatus.SUCCEEDED, output=JobOutput(report_json_path=str(report_path)))
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities")
    assert r.status_code == 200
    data = r.json()
    assert len(data["entities"]) == 1
    assert data["entities"][0]["traceability_status"] == "valid"
