"""SQL Server claim/idempotency for external_image_analysis_requests (Phase 5 corrections)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.domain.image_processing.external_image_analysis_request import (
    ExternalImageAnalysisRequest,
    ExternalRequestStatus,
    build_external_idempotency_key,
)
from src.infrastructure.repositories.sql_external_image_analysis_request_repository import (
    SqlExternalImageAnalysisRequestRepository,
)


@pytest.fixture
def sql_client_or_skip():
    from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config
    from tests.support.sql_integration import sql_server_client_or_skip
    from tests.support.worker_phase1.sql_cleanup import assert_sql_integration_database_is_safe

    try:
        assert_sql_integration_database_is_safe()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    try:
        import pyodbc  # noqa: F401
    except ImportError:
        pytest.skip("pyodbc required for SQL Server integration")
    return sql_server_client_or_skip(resolve_sqlserver_connection_config().connection_string)


def test_sql_external_request_try_claim_unique(sql_client_or_skip) -> None:
    client = sql_client_or_skip
    # Table may be missing if migration 0056 not applied yet.
    with client.cursor() as cur:
        cur.execute(
            "SELECT OBJECT_ID('external_image_analysis_requests', 'U') AS oid"
        )
        row = cur.fetchone()
        if row is None or getattr(row, "oid", None) is None:
            pytest.skip("migration 0056 not applied (external_image_analysis_requests missing)")

    repo = SqlExternalImageAnalysisRequestRepository(client)
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:12]
    key = build_external_idempotency_key(
        job_id=f"job-eiar-{suffix}",
        asset_id=f"asset-eiar-{suffix}",
        provider="gemini",
        model="test-model",
        prompt_version="1",
        configuration_snapshot_version=1,
    )
    first = ExternalImageAnalysisRequest(
        id=str(uuid4()),
        idempotency_key=key,
        job_id=f"job-eiar-{suffix}",
        asset_id=f"asset-eiar-{suffix}",
        provider="gemini",
        model="test-model",
        prompt_key="external_fallback",
        prompt_version="1",
        configuration_snapshot_version=1,
        status=ExternalRequestStatus.CLAIMED,
        created_at=now,
        updated_at=now,
    )
    second = ExternalImageAnalysisRequest(
        id=str(uuid4()),
        idempotency_key=key,
        job_id=first.job_id,
        asset_id=first.asset_id,
        provider="gemini",
        model="test-model",
        prompt_key="external_fallback",
        prompt_version="1",
        configuration_snapshot_version=1,
        status=ExternalRequestStatus.CLAIMED,
        created_at=now,
        updated_at=now,
    )
    try:
        a = repo.try_claim(request=first)
        b = repo.try_claim(request=second)
        assert a.id == first.id
        assert b.id == a.id
        assert b.id != second.id
    finally:
        with client.cursor() as cur:
            cur.execute(
                "DELETE FROM external_image_analysis_requests WHERE idempotency_key = ?",
                (key,),
            )


def test_sql_external_request_try_claim_two_workers_concurrent(sql_client_or_skip) -> None:
    import threading

    client = sql_client_or_skip
    with client.cursor() as cur:
        cur.execute("SELECT OBJECT_ID('external_image_analysis_requests', 'U') AS oid")
        row = cur.fetchone()
        if row is None or getattr(row, "oid", None) is None:
            pytest.skip("migration 0056 not applied (external_image_analysis_requests missing)")

    repo = SqlExternalImageAnalysisRequestRepository(client)
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:12]
    key = build_external_idempotency_key(
        job_id=f"job-eiar-c-{suffix}",
        asset_id=f"asset-eiar-c-{suffix}",
        provider="gemini",
        model="test-model",
        prompt_version="1",
        configuration_snapshot_version=1,
    )

    def _req() -> ExternalImageAnalysisRequest:
        return ExternalImageAnalysisRequest(
            id=str(uuid4()),
            idempotency_key=key,
            job_id=f"job-eiar-c-{suffix}",
            asset_id=f"asset-eiar-c-{suffix}",
            provider="gemini",
            model="test-model",
            prompt_key="external_fallback",
            prompt_version="1",
            configuration_snapshot_version=1,
            status=ExternalRequestStatus.CLAIMED,
            created_at=now,
            updated_at=now,
        )

    barrier = threading.Barrier(2)
    claimed: list[str] = []

    def worker() -> None:
        barrier.wait()
        row = repo.try_claim(request=_req())
        claimed.append(row.id)

    try:
        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(claimed) == 2
        assert claimed[0] == claimed[1]
    finally:
        with client.cursor() as cur:
            cur.execute(
                "DELETE FROM external_image_analysis_requests WHERE idempotency_key = ?",
                (key,),
            )
