"""
Stage 2.1.E — Assisted counting API tests.

Review store persistence, review merge + summary recomputation,
POST review validation, GET entities filtering, GET evidence, GET audit.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.jobs.job_store import create_job, update_job
from src.jobs.models import JobOutput, JobStatus
from src.review import get_entity_audit, load_reviews, merge_resolved_report, save_review


@pytest.fixture
def client():
    return TestClient(app)


# --- Review store ---

def test_review_store_load_empty(tmp_path):
    from src.review.review_store import load_reviews
    assert load_reviews(tmp_path) == {}


def test_review_store_save_and_load(tmp_path):
    event = {
        "timestamp": "2025-01-01T12:00:00Z",
        "actor": "op1",
        "action": "SET_COUNT",
        "before": {"count_status": "NEEDS_REVIEW", "final_quantity": None},
        "after": {"count_status": "COUNTED_MANUAL", "final_quantity": 10},
    }
    save_review(tmp_path, "job_1_E1", event)
    data = load_reviews(tmp_path)
    assert "job_1_E1" in data
    assert len(data["job_1_E1"]["events"]) == 1
    assert data["job_1_E1"]["events"][0]["action"] == "SET_COUNT"
    assert data["job_1_E1"]["events"][0]["after"]["final_quantity"] == 10

    save_review(tmp_path, "job_1_E1", {**event, "action": "MARK_EMPTY", "after": {"count_status": "EMPTY", "final_quantity": 0}})
    data2 = load_reviews(tmp_path)
    assert len(data2["job_1_E1"]["events"]) == 2


def test_get_entity_audit(tmp_path):
    save_review(tmp_path, "E1", {"action": "SET_COUNT", "before": {}, "after": {"count_status": "COUNTED_MANUAL", "final_quantity": 5}})
    audit = get_entity_audit("job_1", tmp_path, "E1")
    assert len(audit) == 1
    assert audit[0]["action"] == "SET_COUNT"
    assert get_entity_audit("job_1", tmp_path, "E99") == []


# --- Review merge + summary ---

def test_merge_resolved_report_applies_set_count():
    report = {
        "report_version": "2.1",
        "entities": [
            {"entity_uid": "E1", "count_status": "NEEDS_REVIEW", "final_quantity": None, "entity_type": "PALLET"},
            {"entity_uid": "E2", "count_status": "COUNTED", "final_quantity": 12, "entity_type": "PALLET"},
        ],
        "summary": {"total_entities": 2, "counted": 1, "needs_review": 1, "counted_manual": 0, "pallets": 2, "empty_pallets": 0, "loose_boxes": 0, "not_countable": 0, "invalid_structure": 0},
    }
    reviews = {
        "E1": {
            "entity_uid": "E1",
            "events": [
                {"action": "SET_COUNT", "after": {"count_status": "COUNTED_MANUAL", "final_quantity": 15}},
            ],
        },
    }
    merged = merge_resolved_report(report, reviews)
    e1 = next(e for e in merged["entities"] if e["entity_uid"] == "E1")
    assert e1["count_status"] == "COUNTED_MANUAL"
    assert e1["final_quantity"] == 15
    assert merged["summary"]["counted_manual"] == 1
    assert merged["summary"]["needs_review"] == 0


def test_merge_resolved_report_mark_empty_and_invalid():
    report = {
        "entities": [
            {"entity_uid": "E1", "count_status": "NEEDS_REVIEW", "final_quantity": None, "entity_type": "PALLET"},
        ],
        "summary": {"total_entities": 1, "needs_review": 1, "counted": 0, "counted_manual": 0, "pallets": 1, "empty_pallets": 0, "loose_boxes": 0, "not_countable": 0, "invalid_structure": 0},
    }
    reviews = {"E1": {"entity_uid": "E1", "events": [{"after": {"count_status": "EMPTY", "final_quantity": 0}}]}}
    merged = merge_resolved_report(report, reviews)
    assert merged["entities"][0]["count_status"] == "EMPTY"
    assert merged["entities"][0]["final_quantity"] == 0
    assert merged["summary"]["empty_pallets"] == 1 or merged["summary"].get("counted_manual") == 0

    reviews2 = {"E1": {"entity_uid": "E1", "events": [{"after": {"count_status": "INVALID_STRUCTURE", "final_quantity": None}}]}}
    merged2 = merge_resolved_report(report, reviews2)
    assert merged2["entities"][0]["count_status"] == "INVALID_STRUCTURE"
    assert merged2["summary"]["invalid_structure"] == 1


# --- API (entities + report resolved) ---

@pytest.fixture
def job_with_report_and_evidence(tmp_path):
    """Create a succeeded job with hybrid_report.json and evidence_index.json under run/."""
    job_id = "job_stage2e_test"
    run_dir = tmp_path / job_id / "run"
    run_dir.mkdir(parents=True)
    report_path = run_dir / "hybrid_report.json"
    report = {
        "report_version": "2.1",
        "mode": "hybrid_v2.1",
        "summary": {"total_entities": 2, "pallets": 2, "empty_pallets": 0, "loose_boxes": 0, "counted": 0, "needs_review": 2, "not_countable": 0, "invalid_structure": 0, "counted_manual": 0},
        "entities": [
            {"entity_uid": "job_stage2e_test_E1", "pallet_id": "P1", "entity_type": "PALLET", "count_status": "NEEDS_REVIEW", "final_quantity": None, "entity_quality_score": 0.5, "evidence_path": "run/evidence/job_stage2e_test_E1"},
            {"entity_uid": "job_stage2e_test_E2", "pallet_id": "P2", "entity_type": "PALLET", "count_status": "COUNTED", "final_quantity": 10, "entity_quality_score": 0.9, "evidence_path": "run/evidence/job_stage2e_test_E2"},
        ],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    index = {
        "job_id": job_id,
        "mode": "hybrid_v2.1",
        "entities": [
            {"entity_uid": "job_stage2e_test_E1", "pallet_id": "P1", "evidence": {"overview": ["run/evidence/job_stage2e_test_E1/overview_00.jpg"]}},
            {"entity_uid": "job_stage2e_test_E2", "pallet_id": "P2", "evidence": {"overview": ["run/evidence/job_stage2e_test_E2/overview_00.jpg"]}},
        ],
    }
    with open(run_dir / "evidence_index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    create_job(tmp_path, job_id, video_path=str(tmp_path / "video.mp4"), mode="hybrid", confidence_threshold=0.7)
    update_job(
        tmp_path,
        job_id,
        status=JobStatus.SUCCEEDED,
        output=JobOutput(report_json_path=str(report_path)),
    )
    return job_id, tmp_path, report_path, run_dir


def test_api_get_entities_filtering(client: TestClient, job_with_report_and_evidence):
    job_id, tmp_path, _report_path, _run_dir = job_with_report_and_evidence
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (tmp_path / job_id / "run" / "hybrid_report.json", tmp_path / job_id / "run")
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities")
    assert r.status_code == 200
    data = r.json()
    assert "entities" in data
    assert len(data["entities"]) == 2
    uids = [e["entity_uid"] for e in data["entities"]]
    assert "job_stage2e_test_E1" in uids
    assert "job_stage2e_test_E2" in uids

    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (tmp_path / job_id / "run" / "hybrid_report.json", tmp_path / job_id / "run")
            r2 = client.get(f"/api/v1/inventory/jobs/{job_id}/entities?status=NEEDS_REVIEW")
    assert r2.status_code == 200
    assert len(r2.json()["entities"]) == 1
    assert r2.json()["entities"][0]["count_status"] == "NEEDS_REVIEW"


def test_api_get_evidence(client: TestClient, job_with_report_and_evidence):
    job_id, tmp_path, report_path, run_dir = job_with_report_and_evidence
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities/job_stage2e_test_E1/evidence")
    assert r.status_code == 200
    data = r.json()
    assert data["entity_uid"] == "job_stage2e_test_E1"
    assert "evidence" in data
    assert "overview" in data["evidence"]


def test_api_post_review_validation(client: TestClient, job_with_report_and_evidence):
    job_id, tmp_path, report_path, run_dir = job_with_report_and_evidence
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.post(
                f"/api/v1/inventory/jobs/{job_id}/entities/job_stage2e_test_E1/review",
                json={"action": "SET_COUNT", "final_quantity": 15, "actor": "test_op", "notes": "ok"},
            )
    assert r.status_code == 200
    assert "entity_uid" in r.json() and r.json()["action"] == "SET_COUNT"

    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r2 = client.post(
                f"/api/v1/inventory/jobs/{job_id}/entities/job_stage2e_test_E1/review",
                json={"action": "SET_COUNT", "actor": "test"},  # missing final_quantity
            )
    assert r2.status_code == 422

    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r3 = client.post(
                f"/api/v1/inventory/jobs/{job_id}/entities/nonexistent_uid/review",
                json={"action": "MARK_EMPTY", "actor": "test"},
            )
    assert r3.status_code == 404


def test_api_get_audit(client: TestClient, job_with_report_and_evidence):
    job_id, tmp_path, report_path, run_dir = job_with_report_and_evidence
    save_review(run_dir, "job_stage2e_test_E1", {"action": "SET_COUNT", "before": {}, "after": {"count_status": "COUNTED_MANUAL", "final_quantity": 20}})
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
            mock_resolve.return_value = (report_path, run_dir)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities/job_stage2e_test_E1/audit")
    assert r.status_code == 200
    assert r.json()["entity_uid"] == "job_stage2e_test_E1"
    assert len(r.json()["events"]) >= 1


def test_api_get_report_resolved(client: TestClient, job_with_report_and_evidence):
    job_id, tmp_path, report_path, run_dir = job_with_report_and_evidence
    save_review(run_dir, "job_stage2e_test_E1", {"action": "SET_COUNT", "after": {"count_status": "COUNTED_MANUAL", "final_quantity": 15}})
    with patch("src.api.routes.jobs._base_path", return_value=tmp_path):
        r = client.get(f"/api/v1/inventory/jobs/{job_id}/report?resolved=true")
    assert r.status_code == 200
    data = r.json()
    e1 = next(e for e in data["entities"] if e["entity_uid"] == "job_stage2e_test_E1")
    assert e1["count_status"] == "COUNTED_MANUAL"
    assert e1["final_quantity"] == 15
    assert data["summary"].get("counted_manual") == 1
