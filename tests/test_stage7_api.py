"""
Stage 7 — API server and job-based processing.

Tests: create job (202 + job_id), status transitions, result endpoint, API key 403.
Mocks engine/worker where needed.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.jobs.job_store import create_job, update_job, get_job
from src.jobs.models import JobStatus


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path


def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_create_job_returns_202_and_job_id(client, output_dir):
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            max_upload_size_mb=500,
            api_key="",
        )
        with patch("src.api.routes.jobs.enqueue"):
            r = client.post(
                "/api/v1/inventory/jobs",
                data={"mode": "hybrid", "confidence_threshold": "0.7"},
                files={"video": ("test.mp4", b"fake_video_content", "video/mp4")},
            )
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["status"] == "queued"
    assert body["mode"] == "hybrid"
    assert body["confidence_threshold"] == 0.7
    assert body["job_id"].startswith("job_")


def test_get_job_status_returns_record(client, output_dir):
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(output_dir=str(output_dir))
        create_job(
            output_dir,
            "job_test123",
            video_path="/tmp/video.mp4",
            mode="hybrid",
            confidence_threshold=0.7,
        )
        r = client.get("/api/v1/inventory/jobs/job_test123")
    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == "job_test123"
    assert data["status"] in ("queued", "running", "succeeded", "failed")
    assert "progress" in data
    assert "created_at" in data


def test_get_job_status_404(client, output_dir):
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(output_dir=str(output_dir))
        r = client.get("/api/v1/inventory/jobs/nonexistent_job_id")
    assert r.status_code == 404


def test_get_job_result_returns_report_when_succeeded(client, output_dir):
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(output_dir=str(output_dir))
        job_id = "job_result_test"
        create_job(output_dir, job_id, video_path="/tmp/v.mp4", mode="hybrid")
        run_dir = output_dir / job_id / "run"
        run_dir.mkdir(parents=True)
        report_path = run_dir / "hybrid_report.json"
        report_data = {"mode": "hybrid", "total_pallets_detected": 2, "pallets": []}
        report_path.write_text(json.dumps(report_data), encoding="utf-8")
        update_job(
            output_dir,
            job_id,
            status=JobStatus.SUCCEEDED,
            output={
                "report_json_path": str(report_path),
                "report_csv_path": None,
                "artifacts_dir": str(output_dir / job_id),
            },
        )
        r = client.get(f"/api/v1/inventory/jobs/{job_id}/result")
    assert r.status_code == 200
    assert r.json()["mode"] == "hybrid"
    assert r.json()["total_pallets_detected"] == 2


def test_get_job_result_409_when_not_succeeded(client, output_dir):
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(output_dir=str(output_dir))
        job_id = "job_running_test"
        create_job(output_dir, job_id, video_path="/tmp/v.mp4", mode="hybrid")
        update_job(output_dir, job_id, status=JobStatus.RUNNING)
        r = client.get(f"/api/v1/inventory/jobs/{job_id}/result")
    assert r.status_code == 409


def test_api_key_missing_returns_403_when_configured(client, output_dir):
    with patch("src.api.server.load_settings") as mock_load:
        mock_load.return_value = MagicMock(api_key="secret-key", output_dir=str(output_dir))
        r = client.post(
            "/api/v1/inventory/jobs",
            data={"mode": "legacy"},
            files={"video": ("x.mp4", b"x", "video/mp4")},
        )
    assert r.status_code == 403


def test_api_key_valid_passes(client, output_dir):
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            max_upload_size_mb=500,
            api_key="secret-key",
        )
        with patch("src.api.server.load_settings", mock_load):
            with patch("src.api.routes.jobs.enqueue"):
                r = client.post(
                    "/api/v1/inventory/jobs",
                    data={"mode": "legacy"},
                    files={"video": ("x.mp4", b"x", "video/mp4")},
                    headers={"X-API-Key": "secret-key"},
                )
    assert r.status_code == 202


def test_create_job_413_when_upload_exceeds_limit(client, output_dir):
    """Streaming save enforces max size; returns 413 and does not leave partial file."""
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            max_upload_size_mb=1 / (1024 * 1024),  # 1 byte
            api_key="",
        )
        with patch("src.api.routes.jobs.enqueue"):
            r = client.post(
                "/api/v1/inventory/jobs",
                data={"mode": "legacy", "confidence_threshold": "0.5"},
                files={"video": ("big.mp4", b"more_than_one_byte", "video/mp4")},
            )
    assert r.status_code == 413
    # No job dir should exist (we never enqueue); or if job_id was created, input file should be removed
    job_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("job_")]
    for job_dir in job_dirs:
        input_dir = job_dir / "input"
        if input_dir.exists():
            assert list(input_dir.iterdir()) == []


def test_create_job_422_invalid_mode(client, output_dir):
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            max_upload_size_mb=500,
            api_key="",
        )
        with patch("src.api.routes.jobs.enqueue"):
            r = client.post(
                "/api/v1/inventory/jobs",
                data={"mode": "invalid_mode", "confidence_threshold": "0.7"},
                files={"video": ("x.mp4", b"x", "video/mp4")},
            )
    assert r.status_code == 422
    assert "legacy" in str(r.json().get("detail", ""))


def test_create_job_422_invalid_metadata(client, output_dir):
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            max_upload_size_mb=500,
            api_key="",
        )
        with patch("src.api.routes.jobs.enqueue"):
            r = client.post(
                "/api/v1/inventory/jobs",
                data={"mode": "legacy", "confidence_threshold": "0.7", "metadata": "not valid json"},
                files={"video": ("x.mp4", b"x", "video/mp4")},
            )
    assert r.status_code == 422
    assert "json" in str(r.json().get("detail", "")).lower()
