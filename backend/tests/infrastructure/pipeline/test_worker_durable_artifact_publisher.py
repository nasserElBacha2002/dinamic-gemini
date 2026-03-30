"""Tests for Phase 3B worker durable artifact publishing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
    DURABLE_ARTIFACT_KIND_EXECUTION_LOG,
    DURABLE_ARTIFACT_KIND_HYBRID_REPORT_CSV,
    DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON,
    WORKER_DURABLE_LOGICAL_PREFIX_ROOT,
    publish_worker_durable_artifacts,
    worker_durable_artifact_key_prefix,
    worker_output_storage_keys,
)
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter


def test_canonical_storage_keys_single_run_segment_no_duplication() -> None:
    """Keys must be v3/jobs/{job_id}/{run_segment}/<file> — never .../run/run/... for default segment."""
    job_id = "job-abc"
    keys = worker_output_storage_keys(job_id, DEFAULT_V3_WORKER_RUN_SEGMENT)
    prefix = worker_durable_artifact_key_prefix(job_id, DEFAULT_V3_WORKER_RUN_SEGMENT)
    assert prefix == f"{WORKER_DURABLE_LOGICAL_PREFIX_ROOT}/{job_id}/{DEFAULT_V3_WORKER_RUN_SEGMENT}"
    assert keys[DURABLE_ARTIFACT_KIND_EXECUTION_LOG] == f"{prefix}/execution_log.jsonl"
    assert keys[DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON] == f"{prefix}/hybrid_report.json"
    assert keys[DURABLE_ARTIFACT_KIND_HYBRID_REPORT_CSV] == f"{prefix}/hybrid_report.csv"
    assert f"/{DEFAULT_V3_WORKER_RUN_SEGMENT}/{DEFAULT_V3_WORKER_RUN_SEGMENT}/" not in keys[
        DURABLE_ARTIFACT_KIND_EXECUTION_LOG
    ]


def test_worker_output_storage_keys_alternate_run_segment() -> None:
    keys = worker_output_storage_keys("job-abc", "custom-run")
    assert keys[DURABLE_ARTIFACT_KIND_EXECUTION_LOG] == "v3/jobs/job-abc/custom-run/execution_log.jsonl"


def test_publish_local_provider_writes_expected_keys(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "execution_log.jsonl").write_text('{"ts":"t","stage":"s","level":"info","message":"m"}\n')
    (run_dir / "hybrid_report.json").write_text('{"entities":[]}', encoding="utf-8")
    (run_dir / "hybrid_report.csv").write_text("a,b\n", encoding="utf-8")

    base = tmp_path / "store"
    store = V3ArtifactStorageAdapter(base)
    meta = publish_worker_durable_artifacts(
        store,
        job_id="jid",
        run_segment="run",
        run_dir=run_dir,
    )

    assert DURABLE_ARTIFACT_KIND_EXECUTION_LOG in meta
    assert DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON in meta
    assert DURABLE_ARTIFACT_KIND_HYBRID_REPORT_CSV in meta
    log_info = meta[DURABLE_ARTIFACT_KIND_EXECUTION_LOG]
    assert log_info["storage_provider"] == "local"
    expected = worker_output_storage_keys("jid", "run")[DURABLE_ARTIFACT_KIND_EXECUTION_LOG]
    assert log_info["storage_key"] == expected
    assert (base / log_info["storage_key"]).is_file()
    assert (base / meta[DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON]["storage_key"]).is_file()


def test_publish_skips_optional_csv_when_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "execution_log.jsonl").write_text('{"ts":"t","stage":"s","level":"info","message":"m"}\n')
    (run_dir / "hybrid_report.json").write_text("{}", encoding="utf-8")

    store = V3ArtifactStorageAdapter(tmp_path / "store")
    meta = publish_worker_durable_artifacts(
        store,
        job_id="j",
        run_segment="run",
        run_dir=run_dir,
    )
    assert DURABLE_ARTIFACT_KIND_HYBRID_REPORT_CSV not in meta


def test_publish_requires_execution_log(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "hybrid_report.json").write_text("{}", encoding="utf-8")

    store = V3ArtifactStorageAdapter(tmp_path / "store")
    with pytest.raises(FileNotFoundError, match="execution_log"):
        publish_worker_durable_artifacts(store, job_id="j", run_segment="run", run_dir=run_dir)


def test_publish_only_intended_keys_no_extra_uploads(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "execution_log.jsonl").write_text('{"ts":"t","stage":"s","level":"info","message":"m"}\n')
    (run_dir / "hybrid_report.json").write_text("{}", encoding="utf-8")
    (run_dir / "input_manifest.json").write_text("{}", encoding="utf-8")
    (run_dir / "noise.bin").write_bytes(b"x")

    mock_store = MagicMock()
    from src.infrastructure.storage.artifact_store import StoredArtifact

    def _put(key: str, fh, content_type: str) -> StoredArtifact:
        data = fh.read()
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket="b",
            storage_key=key,
            content_type=content_type,
            file_size_bytes=len(data),
            etag="e",
        )

    mock_store.put_object.side_effect = _put
    meta = publish_worker_durable_artifacts(
        mock_store,
        job_id="j1",
        run_segment="run",
        run_dir=run_dir,
    )
    assert mock_store.put_object.call_count == 2  # csv missing
    uploaded_keys = {c.args[0] for c in mock_store.put_object.call_args_list}
    wk = worker_output_storage_keys("j1", "run")
    assert uploaded_keys == {
        wk[DURABLE_ARTIFACT_KIND_EXECUTION_LOG],
        wk[DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON],
    }
    assert "input_manifest.json" not in str(uploaded_keys)
    assert meta[DURABLE_ARTIFACT_KIND_EXECUTION_LOG]["storage_bucket"] == "b"
