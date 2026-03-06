"""
Stage 7 — API server and job-based processing.
Stage 2.2.A — Photos input: create job with JSON body (photos), validation, manifest.
"""

import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.jobs.job_store import create_job, update_job, get_job
from src.jobs.models import JobStatus
from src.jobs.worker import run_job


def _minimal_jpeg_base64() -> str:
    """Return base64 of a minimal valid JPEG (legacy helper; prefer _minimal_jpeg_bytes for form-data)."""
    return base64.b64encode(_minimal_jpeg_bytes()).decode("ascii")


def _minimal_jpeg_bytes() -> bytes:
    """Return raw bytes of a minimal valid JPEG (for form-data photos tests)."""
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


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
            data={"mode": "hybrid"},
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
                    data={"mode": "hybrid"},
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
                data={"mode": "hybrid", "confidence_threshold": "0.5"},
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
    detail = str(r.json().get("detail", ""))
    assert "mode" in detail.lower() or "hybrid" in detail


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
                data={"mode": "hybrid", "confidence_threshold": "0.7", "metadata": "not valid json"},
                files={"video": ("x.mp4", b"x", "video/mp4")},
            )
    assert r.status_code == 422
    assert "json" in str(r.json().get("detail", "")).lower()


def test_get_job_status_400_invalid_job_id_path_traversal(client):
    """Invalid job_id (path traversal) must return 400."""
    r = client.get("/api/v1/inventory/jobs/..")
    assert r.status_code == 400
    assert "detail" in r.json()


# ---------- Stage 2.2.A — Photos input (form-data) ----------


def test_create_job_photos_returns_202_and_writes_manifest(client, output_dir):
    """POST form-data with input_type=photos and multiple 'photos' files creates job and manifest."""
    jpeg = _minimal_jpeg_bytes()
    data = {"input_type": "photos", "mode": "hybrid", "confidence_threshold": "0.7"}
    files = [
        ("photos", ("img_001.jpg", jpeg, "image/jpeg")),
        ("photos", ("img_002.jpg", jpeg, "image/jpeg")),
    ]
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            max_upload_size_mb=500,
            api_key="",
            enable_photos_input=True,
            max_photos_per_job=12,
            photos_max_total_bytes=25 * 1024 * 1024,
        )
        with patch("src.api.routes.jobs.enqueue"):
            r = client.post("/api/v1/inventory/jobs", data=data, files=files)
    assert r.status_code == 202
    body = r.json()
    assert body["job_id"].startswith("job_")
    assert body["status"] == "queued"
    assert body["mode"] == "hybrid"
    job_id = body["job_id"]
    job_dir = output_dir / job_id
    run_dir = job_dir / "run"
    input_photos = run_dir / "input_photos"
    manifest_path = run_dir / "input_manifest.json"
    assert input_photos.is_dir()
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["input_type"] == "photos"
    assert manifest["total_photos"] == 2
    assert "total_bytes_original" in manifest
    assert len(manifest["photos"]) == 2
    assert manifest["photos"][0]["original_filename"] == "img_001.jpg"
    assert manifest["photos"][0]["stored_filename"].startswith("0001_")
    assert manifest["photos"][0]["stored_filename"].endswith(".jpg")
    job_json = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert job_json["input"]["input_type"] == "photos"
    assert job_json["input"]["input_manifest_path"] == "run/input_manifest.json"
    assert job_json["input"]["photos_dir"] == "run/input_photos"
    assert job_json["input"]["video_path"] == ""


def test_create_job_photos_invalid_image_bytes_422(client, output_dir):
    """Non-image file content is rejected with 422."""
    data = {"input_type": "photos", "mode": "hybrid"}
    files = [("photos", ("a.jpg", b"not an image", "image/jpeg"))]
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            api_key="",
            enable_photos_input=True,
            max_photos_per_job=12,
            photos_max_total_bytes=10 * 1024 * 1024,
        )
        r = client.post("/api/v1/inventory/jobs", data=data, files=files)
    assert r.status_code == 422
    detail = str(r.json().get("detail", ""))
    assert "valid" in detail.lower() or "image" in detail.lower()


def test_create_job_photos_too_many_422(client, output_dir):
    jpeg = _minimal_jpeg_bytes()
    data = {"input_type": "photos", "mode": "hybrid"}
    files = [("photos", (f"img_{i}.jpg", jpeg, "image/jpeg")) for i in range(1, 4)]
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            api_key="",
            enable_photos_input=True,
            max_photos_per_job=2,
            photos_max_total_bytes=25 * 1024 * 1024,
        )
        r = client.post("/api/v1/inventory/jobs", data=data, files=files)
    assert r.status_code == 422
    assert "too many" in str(r.json().get("detail", "")).lower()


def test_create_job_photos_too_large_total_bytes_422(client, output_dir):
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    big_jpeg = buf.tobytes()
    data = {"input_type": "photos", "mode": "hybrid"}
    files = [("photos", ("big.jpg", big_jpeg, "image/jpeg"))]
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            api_key="",
            enable_photos_input=True,
            max_photos_per_job=12,
            photos_max_total_bytes=100,
        )
        r = client.post("/api/v1/inventory/jobs", data=data, files=files)
    assert r.status_code == 422
    assert "exceed" in str(r.json().get("detail", "")).lower() or "limit" in str(r.json().get("detail", "")).lower()


def test_create_job_photos_unsafe_filename_stored_safely(client, output_dir):
    """Filename with ../ or \\ is sanitized; file written only under run/input_photos/."""
    jpeg = _minimal_jpeg_bytes()
    data = {"input_type": "photos", "mode": "hybrid"}
    files = [("photos", ("../../etc/passwd.jpg", jpeg, "image/jpeg"))]
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            api_key="",
            enable_photos_input=True,
            max_photos_per_job=12,
            photos_max_total_bytes=25 * 1024 * 1024,
        )
        with patch("src.api.routes.jobs.enqueue"):
            r = client.post("/api/v1/inventory/jobs", data=data, files=files)
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    run_dir = output_dir / job_id / "run"
    input_photos = run_dir / "input_photos"
    assert input_photos.is_dir()
    files_list = list(input_photos.iterdir())
    assert len(files_list) == 1
    assert files_list[0].name.startswith("0001_")
    assert files_list[0].name.endswith(".jpg")
    assert ".." not in files_list[0].name
    assert "passwd" in files_list[0].name or "etc" in files_list[0].name or "image" in files_list[0].name


def test_create_job_photos_disabled_422(client, output_dir):
    jpeg = _minimal_jpeg_bytes()
    data = {"input_type": "photos", "mode": "hybrid"}
    files = [("photos", ("a.jpg", jpeg, "image/jpeg"))]
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            api_key="",
            enable_photos_input=False,
            max_photos_per_job=12,
            photos_max_total_bytes=25 * 1024 * 1024,
        )
        r = client.post("/api/v1/inventory/jobs", data=data, files=files)
    assert r.status_code == 422
    assert "disabled" in str(r.json().get("detail", "")).lower() or "ENABLE_PHOTOS" in str(r.json().get("detail", ""))


def test_create_job_photos_mode_legacy_422(client, output_dir):
    """Request with mode=legacy must be rejected (legacy removed as of v2.2)."""
    jpeg = _minimal_jpeg_bytes()
    data = {"input_type": "photos", "mode": "legacy"}
    files = [("photos", ("a.jpg", jpeg, "image/jpeg"))]
    with patch("src.api.routes.jobs.load_settings") as mock_load:
        mock_load.return_value = MagicMock(
            output_dir=str(output_dir),
            api_key="",
            enable_photos_input=True,
            max_photos_per_job=12,
            photos_max_total_bytes=25 * 1024 * 1024,
        )
        r = client.post("/api/v1/inventory/jobs", data=data, files=files)
    assert r.status_code == 422
    assert "legacy" in str(r.json().get("detail", "")).lower()
    assert "hybrid" in str(r.json().get("detail", "")).lower()


def test_worker_photos_job_fails_when_manifest_missing(output_dir):
    """Photos job without run_dir/manifest fails with clear error (FrameSource raises)."""
    create_job(
        output_dir,
        "job_photos_test",
        video_path="",
        mode="hybrid",
        confidence_threshold=0.7,
        input_type="photos",
        input_manifest_path="run/input_manifest.json",
        photos_dir="run/input_photos",
    )
    run_job(Path(output_dir), "job_photos_test")
    record = get_job(output_dir, "job_photos_test")
    assert record is not None
    assert record.status == JobStatus.FAILED
    err = (record.error or "").lower()
    # Worker stores generic "Pipeline exited with code 1"; FrameSource may log "manifest not found"
    assert "manifest" in err or "not found" in err or "frame" in err or "code 1" in err or "pipeline" in err


def test_worker_photos_with_legacy_mode_rejected(output_dir):
    """When job has mode=legacy, worker marks job FAILED with clear error (no pipeline run)."""
    create_job(
        output_dir,
        "job_photos_legacy",
        video_path="",
        mode="legacy",
        confidence_threshold=0.7,
        input_type="photos",
    )
    run_job(Path(output_dir), "job_photos_legacy")
    record = get_job(output_dir, "job_photos_legacy")
    assert record is not None
    assert record.status == JobStatus.FAILED
    assert "legacy" in (record.error or "").lower()
    assert "hybrid" in (record.error or "").lower()
    assert "video" in (record.error or "").lower()
