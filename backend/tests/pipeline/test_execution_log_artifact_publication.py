"""Artifact dispatcher validates execution_log JSONL before staging."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.application.services.artifact_publication_dispatcher import (
    ArtifactPublicationDispatcher,
    ArtifactSourceStagingFailedError,
)


class _FakeStaging:
    def put_exact_source(self, *, job_id: str, artifact_kind: str, file_obj):
        return type(
            "Staged",
            (),
            {
                "staging_key": f"staging/{job_id}/{artifact_kind}",
                "source_sha256": "abc",
                "size_bytes": 10,
            },
        )()


class _FakeManifest:
    def ensure_expected_entries(self, job_id: str, *, now) -> None:
        return None


class _FakeOutbox:
    def ensure_publication_work(self, *, entry, now):
        return entry


class _FakeClock:
    def now(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)


def test_register_publication_work_rejects_invalid_execution_log_jsonl() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        bad_log = run_dir / "execution_log.jsonl"
        bad_log.write_text("not-json\n", encoding="utf-8")

        dispatcher = ArtifactPublicationDispatcher(
            outbox_store=_FakeOutbox(),
            manifest_store=_FakeManifest(),
            stage_store=object(),
            artifact_store=object(),
            stage_recorder=None,
            continuation=None,
            automatic_continuation=None,
            staging_store=_FakeStaging(),
            reconciler=None,
            clock=_FakeClock(),
        )

        with pytest.raises(ArtifactSourceStagingFailedError, match="execution_log artifact invalid"):
            dispatcher.register_publication_work(
                job_id="job-1",
                run_segment="run",
                run_dir=run_dir,
            )
