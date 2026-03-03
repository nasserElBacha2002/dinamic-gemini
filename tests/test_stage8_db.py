"""
Stage 8 — SQL Server persistence (optional).

Tests use mocks; no real SQL Server required.
- insert_pallet_results quantity selection (dict + object, final_quantity preferred).
- API uses DB as source of truth when enabled: GET status, GET result, GET artifacts.
- POST with DB enabled calls create_job (job_store inserts into DB).
- Worker calls set_job_outputs + insert_pallet_results on success; ERROR event on exception.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.database.repository import PalletResultsRepository
from src.jobs.job_store import get_job
from src.jobs.worker import run_job, _push_success_to_db


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path


def test_get_job_returns_from_db_when_enabled(output_dir):
    """When _db_repos returns repos, get_job uses jobs_repo.get_job and returns JobRecord."""
    mock_jobs = MagicMock()
    mock_jobs.get_job.return_value = {
        "job_id": "job_db123",
        "input": {
            "video_path": "/tmp/v.mp4",
            "mode": "hybrid",
            "confidence_threshold": 0.75,
            "metadata": None,
        },
        "status": "succeeded",
        "progress": {"stage": "done", "percent": 100},
        "output": {"report_json_path": "/out/job_db123/run/hybrid_report.json", "report_csv_path": None, "artifacts_dir": "/out/job_db123"},
        "error": None,
        "created_at": "2025-01-01T12:00:00Z",
        "updated_at": "2025-01-01T12:01:00Z",
    }
    with patch("src.jobs.job_store._db_repos") as m_repos:
        m_repos.return_value = (mock_jobs, MagicMock(), MagicMock())
        record = get_job(output_dir, "job_db123")
    assert record is not None
    assert record.job_id == "job_db123"
    assert record.status.value == "succeeded"
    mock_jobs.get_job.assert_called_once_with("job_db123")


def test_push_success_to_db_calls_set_job_outputs_and_insert_pallet_results(output_dir):
    """_push_success_to_db calls set_job_outputs and insert_pallet_results when report has pallets."""
    report_path = output_dir / "hybrid_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "frames_selected": 10,
        "prompt_version": "global_min_v1",
        "metrics": {"total_calls": 2, "fallback_attempts": 1},
        "pallets": [
            {"pallet_id": "P1", "internal_code": "X", "quantity": 5, "source": "label", "confidence": 0.9, "fallback_used": False, "estimated_visible_boxes": None},
        ],
    }
    report_path.write_text(json.dumps(report_data), encoding="utf-8")

    mock_jobs = MagicMock()
    mock_pallet = MagicMock()
    mock_events = MagicMock()
    with patch("src.jobs.worker._db_repos") as m_repos:
        m_repos.return_value = (mock_jobs, mock_pallet, mock_events)
        _push_success_to_db("job_xyz", report_path, None, str(output_dir))

    mock_jobs.set_job_outputs.assert_called_once()
    call_kw = mock_jobs.set_job_outputs.call_args[1]
    assert call_kw["frames_count_sent"] == 10
    assert call_kw["gemini_calls"] == 2
    assert call_kw["prompt_version"] == "global_min_v1"
    mock_pallet.insert_pallet_results.assert_called_once_with("job_xyz", report_data["pallets"])
    assert mock_events.insert_event.call_count >= 3  # FRAMES_SELECTED, GEMINI_GLOBAL_CALL, FALLBACK_RUN, REPORT_WRITTEN


def test_worker_inserts_error_event_on_exception(output_dir):
    """When run_job raises, update_job is called with failed and events_repo.insert_event(ERROR) is called."""
    from src.jobs.job_store import create_job

    create_job(
        output_dir,
        "job_fail",
        video_path=str(output_dir / "input" / "v.mp4"),
        mode="hybrid",
        confidence_threshold=0.7,
    )
    (output_dir / "job_fail" / "input").mkdir(parents=True, exist_ok=True)

    mock_jobs = MagicMock()
    mock_pallet = MagicMock()
    mock_events = MagicMock()
    with patch("src.jobs.worker._db_repos") as m_repos:
        m_repos.return_value = (mock_jobs, mock_pallet, mock_events)
        with patch("src.jobs.worker.HybridInventoryPipeline") as m_pipeline:
            m_pipeline.return_value.process_video.side_effect = RuntimeError("simulated failure")
            run_job(output_dir, "job_fail")

    mock_events.insert_event.assert_called()
    error_calls = [c for c in mock_events.insert_event.call_args_list if len(c[0]) >= 2 and c[0][1] == "ERROR"]
    assert len(error_calls) >= 1
    payload = error_calls[0][0][2] if len(error_calls[0][0]) > 2 else {}
    assert "simulated failure" in str(payload.get("message", ""))


# --- insert_pallet_results quantity logic (dict + object) ---


def test_insert_pallet_results_quantity_dict_final_quantity_preferred():
    """Dict: quantity_to_store = final_quantity if not None else quantity."""
    mock_client = MagicMock()
    mock_cursor = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_cursor
    mock_cm.__exit__.return_value = None
    mock_client.cursor.return_value = mock_cm
    repo = PalletResultsRepository(mock_client)
    pallets = [
        {"pallet_id": "P1", "final_quantity": 10, "quantity": 5, "source": "label", "confidence": 0.9, "fallback_used": False},
        {"pallet_id": "P2", "quantity": 3, "source": "fallback", "confidence": 0.8, "fallback_used": True},
        {"pallet_id": "P3", "final_quantity": None, "quantity": 7, "source": "label", "confidence": 1.0, "fallback_used": False},
    ]
    repo.insert_pallet_results("job_1", pallets)
    assert mock_cursor.execute.call_count == 3
    # P1: final_quantity 10
    assert mock_cursor.execute.call_args_list[0][0][1][3] == 10
    # P2: quantity 3
    assert mock_cursor.execute.call_args_list[1][0][1][3] == 3
    # P3: final_quantity None -> quantity 7
    assert mock_cursor.execute.call_args_list[2][0][1][3] == 7


def test_insert_pallet_results_quantity_object_final_quantity_preferred():
    """Object: quantity_to_store = final_quantity if not None else quantity; raw_estimated_visible_boxes from estimated_visible_boxes."""
    mock_client = MagicMock()
    mock_cursor = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_cursor
    mock_cm.__exit__.return_value = None
    mock_client.cursor.return_value = mock_cm
    repo = PalletResultsRepository(mock_client)
    P = SimpleNamespace
    pallets = [
        P(pallet_id="P1", internal_code="X", final_quantity=12, quantity=5, source="label", confidence=0.9, fallback_used=False, estimated_visible_boxes=10),
    ]
    repo.insert_pallet_results("job_1", pallets)
    mock_cursor.execute.assert_called_once()
    args = mock_cursor.execute.call_args[0][1]
    assert args[3] == 12  # quantity_to_store
    assert args[8] == 10  # raw_estimated_visible_boxes


# --- API uses DB when enabled (mock _get_db_repos) ---


@pytest.fixture
def client():
    return TestClient(app)


def test_get_status_uses_db_when_enabled(client, output_dir):
    """GET /jobs/{id} when _get_db_repos returns repos uses jobs_repo.get_job."""
    mock_jobs = MagicMock()
    mock_jobs.get_job.return_value = {
        "job_id": "job_api1",
        "input": {"video_path": "/v", "mode": "hybrid", "confidence_threshold": 0.7, "metadata": None},
        "status": "running",
        "progress": {"stage": "gemini_global_call", "percent": 50},
        "output": None,
        "error": None,
        "created_at": "2025-01-01T12:00:00Z",
        "updated_at": "2025-01-01T12:00:01Z",
    }
    with patch("src.api.routes.jobs.load_settings") as m_settings:
        m_settings.return_value = MagicMock(output_dir=str(output_dir))
        with patch("src.api.routes.jobs._get_db_repos") as m_repos:
            m_repos.return_value = (mock_jobs, MagicMock(), MagicMock())
            r = client.get("/api/v1/inventory/jobs/job_api1")
    assert r.status_code == 200
    assert r.json()["job_id"] == "job_api1"
    assert r.json()["status"] == "running"
    mock_jobs.get_job.assert_called_once_with("job_api1")


def test_get_result_uses_db_when_enabled(client, output_dir):
    """GET /jobs/{id}/result when DB enabled uses jobs_repo.get_job + pallet_repo.get_pallet_results."""
    mock_jobs = MagicMock()
    mock_jobs.get_job.return_value = {
        "job_id": "job_res1",
        "input": {"video_path": "/v", "mode": "hybrid", "confidence_threshold": 0.75, "metadata": None},
        "status": "succeeded",
        "progress": {"stage": "done", "percent": 100},
        "output": {"report_json_path": None, "report_csv_path": None, "artifacts_dir": str(output_dir)},
        "error": None,
        "created_at": "2025-01-01T12:00:00Z",
        "updated_at": "2025-01-01T12:01:00Z",
    }
    mock_pallet = MagicMock()
    mock_pallet.get_pallet_results.return_value = [
        {"pallet_id": "P1", "internal_code": "X", "quantity": 5, "source": "label", "confidence": 0.9, "fallback_used": False, "raw_estimated_visible_boxes": None},
    ]
    with patch("src.api.routes.jobs.load_settings") as m_settings:
        m_settings.return_value = MagicMock(output_dir=str(output_dir))
        with patch("src.api.routes.jobs._get_db_repos") as m_repos:
            m_repos.return_value = (mock_jobs, mock_pallet, MagicMock())
            r = client.get("/api/v1/inventory/jobs/job_res1/result")
    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == "job_res1"
    assert data["status"] == "succeeded"
    assert data["total_pallets_detected"] == 1
    assert data["pallets"][0]["pallet_id"] == "P1"
    assert data["pallets"][0]["quantity"] == 5
    mock_jobs.get_job.assert_called_once_with("job_res1")
    mock_pallet.get_pallet_results.assert_called_once_with("job_res1")


def test_post_job_with_db_enabled_calls_create_job(client, output_dir):
    """POST /jobs with DB enabled: job_store.create_job is called and inserts into DB (mock _db_repos)."""
    with patch("src.api.routes.jobs.load_settings") as m_settings:
        m_settings.return_value = MagicMock(
            output_dir=str(output_dir),
            max_upload_size_mb=500,
            api_key="",
        )
        with patch("src.api.routes.jobs.enqueue"):
            mock_jobs = MagicMock()
            with patch("src.jobs.job_store._db_repos") as m_db_repos:
                m_db_repos.return_value = (mock_jobs, MagicMock(), MagicMock())
                r = client.post(
                    "/api/v1/inventory/jobs",
                    data={"mode": "hybrid", "confidence_threshold": "0.7"},
                    files={"video": ("test.mp4", b"fake", "video/mp4")},
                )
    assert r.status_code == 202
    assert r.json()["job_id"].startswith("job_")
    mock_jobs.create_job.assert_called_once()
    call_kw = mock_jobs.create_job.call_args[1]
    assert call_kw["mode"] == "hybrid"
    assert call_kw["confidence_threshold"] == 0.7
