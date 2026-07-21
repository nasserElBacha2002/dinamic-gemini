"""Unit tests for SqlGlobalFallbackBatchRequestRepository cursor API wiring."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from src.domain.image_processing.global_fallback_batch_request import (
    GlobalFallbackBatchRequest,
    GlobalFallbackBatchStatus,
)
from src.infrastructure.repositories.sql_global_fallback_batch_request_repository import (
    SqlGlobalFallbackBatchRequestRepository,
)


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self._fetchone: Any = None
        self._fetchall: list[Any] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> Any:
        return self._fetchone

    def fetchall(self) -> list[Any]:
        return list(self._fetchall)


class _FakeClient:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self):  # noqa: ANN201 — context manager like SqlServerClient
        cur = self._cursor

        class _CM:
            def __enter__(self) -> _FakeCursor:
                return cur

            def __exit__(self, *args: object) -> None:
                return None

        return _CM()


def _sample_request() -> GlobalFallbackBatchRequest:
    now = datetime.now(timezone.utc)
    return GlobalFallbackBatchRequest(
        id="req-1",
        job_id="job-1",
        execution_id="exec-1",
        attempt=1,
        batch_index=0,
        batch_count=1,
        batch_fingerprint="fp-1",
        status=GlobalFallbackBatchStatus.PREPARED,
        ordered_asset_ids=["a1"],
        provider="claude",
        model="m",
        schema_version="v2.1",
        configuration_fingerprint="cfg",
        prompt_fingerprint="prf",
        prepared_image_hashes=["h1"],
        created_at=now,
        updated_at=now,
    )


def test_get_by_fingerprint_uses_cursor_fetchone_not_fetch_all() -> None:
    cur = _FakeCursor()
    cur._fetchone = None
    repo = SqlGlobalFallbackBatchRequestRepository(_FakeClient(cur))  # type: ignore[arg-type]
    assert (
        repo.get_by_fingerprint(
            job_id="job-1", execution_id="exec-1", batch_fingerprint="fp-1"
        )
        is None
    )
    assert len(cur.executed) == 1
    sql, params = cur.executed[0]
    assert "global_fallback_batch_requests" in sql
    assert "?" in sql
    assert ":job_id" not in sql
    assert params == ("job-1", "exec-1", "fp-1")


def test_try_insert_inserts_with_qmark_placeholders() -> None:
    cur = _FakeCursor()
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        id="req-1",
        job_id="job-1",
        execution_id="exec-1",
        attempt=1,
        batch_index=0,
        batch_count=1,
        batch_fingerprint="fp-1",
        status="PREPARED",
        ordered_asset_ids_json='["a1"]',
        provider="claude",
        model="m",
        schema_version="v2.1",
        configuration_fingerprint="cfg",
        prompt_fingerprint="prf",
        prepared_image_hashes_json='["h1"]',
        provider_request_id=None,
        response_sha256=None,
        normalized_response_json=None,
        frame_to_asset_map_json="{}",
        merge_plan_json=None,
        applied_operation_keys_json="[]",
        error_code=None,
        error_message=None,
        worker_token=None,
        estimated_cost=None,
        prompt_tokens=None,
        response_tokens=None,
        duration_ms=None,
        created_at=now,
        updated_at=now,
    )
    # fingerprint miss, save existing miss, reload after insert
    cur.fetchone = MagicMock(side_effect=[None, None, row])  # type: ignore[method-assign]

    repo = SqlGlobalFallbackBatchRequestRepository(_FakeClient(cur))  # type: ignore[arg-type]
    out = repo.try_insert(_sample_request())
    assert out is not None
    assert out.id == "req-1"
    insert_calls = [
        c for c in cur.executed if "INSERT INTO global_fallback_batch_requests" in c[0]
    ]
    assert len(insert_calls) == 1
    assert "?" in insert_calls[0][0]
    assert ":id" not in insert_calls[0][0]


def test_repository_uses_client_cursor_api() -> None:
    """Regression: must use SqlServerClient.cursor(), not a non-existent fetch helper."""
    import inspect

    import src.infrastructure.repositories.sql_global_fallback_batch_request_repository as mod

    src = inspect.getsource(mod.SqlGlobalFallbackBatchRequestRepository)
    assert "self._client.cursor()" in src
    assert "self._sql" not in src
    assert ".fetch_all(" not in src
