from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.application.services.job_stale_reconciler import STALE_FAILURE_CODE
from src.domain.jobs.claim import JobClaimOutcome
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository


class RecordingCursor:
    def __init__(self, rowcounts: list[int]) -> None:
        self._rowcounts = rowcounts
        self.executions: list[tuple[str, tuple]] = []
        self.rowcount = 0

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executions.append((sql, params))
        if self._rowcounts:
            self.rowcount = self._rowcounts.pop(0)
        else:
            self.rowcount = 0


class RecordingClient:
    def __init__(self, rowcounts: list[int]) -> None:
        self.cursor_instance = RecordingCursor(rowcounts=rowcounts)

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance


def _make_job() -> Job:
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
    return Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=None,
        last_heartbeat_at=now,
        cancel_requested_at=None,
        current_stage="worker_launch",
        current_substep="spawn_requested",
        current_step_started_at=now,
        attempt_count=1,
        retry_of_job_id="job-0",
        failure_code=None,
        failure_message=None,
        execution_id="exec-1",
    )


def test_save_insert_placeholder_count_matches_parameters_for_starting_job() -> None:
    client = RecordingClient(rowcounts=[0, 1])
    repo = SqlJobRepository(client)  # type: ignore[arg-type]

    repo.save(_make_job())

    assert len(client.cursor_instance.executions) == 2
    insert_sql, insert_params = client.cursor_instance.executions[1]
    assert "INSERT INTO inventory_jobs" in insert_sql
    # 36 base columns + claim_owner_id + 4 Phase 1 aisle identification snapshot columns
    # + 3 Phase 3 lease fencing columns.
    assert insert_sql.count("?") == len(insert_params) == 44


def test_save_update_placeholder_count_matches_parameters() -> None:
    client = RecordingClient(rowcounts=[1])
    repo = SqlJobRepository(client)  # type: ignore[arg-type]

    repo.save(_make_job())

    assert len(client.cursor_instance.executions) == 1
    update_sql, update_params = client.cursor_instance.executions[0]
    assert "UPDATE inventory_jobs" in update_sql
    # 36 SET columns including claim_owner_id + WHERE id (id excluded from SET count previously 39)
    # + 3 Phase 3 lease fencing columns.
    assert update_sql.count("?") == len(update_params) == 43


class _TxnCursor:
    def __init__(self, script: list[dict]) -> None:
        self._script = list(script)
        self.executions: list[tuple[str, tuple]] = []
        self.rowcount = 0
        self._closed = False

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executions.append((sql, params))
        step = self._script.pop(0) if self._script else {}
        self.rowcount = int(step.get("rowcount", 0))
        self._next_rows = step.get("rows", [])
        if step.get("raise"):
            raise step["raise"]

    def fetchone(self):
        if not getattr(self, "_next_rows", None):
            return None
        return self._next_rows.pop(0)

    def close(self) -> None:
        self._closed = True


class _TxnConnection:
    def __init__(self, script: list[dict]) -> None:
        self.cursor_obj = _TxnCursor(script)

    def cursor(self) -> _TxnCursor:
        return self.cursor_obj


class _FakeTxn:
    def __init__(self, script: list[dict]) -> None:
        self.connection = _TxnConnection(script)
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> _FakeTxn:
        return self

    def __exit__(self, *args) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _ClaimClient:
    def __init__(self, script: list[dict], *, post_rows: list | None = None) -> None:
        self._script = script
        self.last_txn: _FakeTxn | None = None
        self._post_rows = post_rows or []

    def begin_transaction(self) -> _FakeTxn:
        self.last_txn = _FakeTxn(self._script)
        return self.last_txn

    @contextmanager
    def cursor(self):
        cur = MagicMock()
        cur.fetchone.side_effect = list(self._post_rows) + [None]
        cur.rowcount = 1
        yield cur


def test_try_claim_emits_cas_and_commits_when_job_and_aisle_update() -> None:
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
    script = [
        {"rows": [SimpleNamespace(target_type="aisle", target_id="aisle-1", status="starting")]},
        {"rows": [SimpleNamespace(status="queued")]},
        {"rowcount": 1},  # job CAS
        {"rowcount": 1},  # aisle update
    ]
    job = _make_job()
    job.status = JobStatus.RUNNING
    job.claim_owner_id = "owner-1"
    client = _ClaimClient(script, post_rows=[_job_row_ns(job)])
    repo = SqlJobRepository(client)  # type: ignore[arg-type]
    # Bypass full row mapping: stub get_by_id after commit path
    repo.get_by_id = MagicMock(return_value=job)  # type: ignore[method-assign]

    result = repo.try_claim_starting_to_running(
        "job-1", now=now, claim_owner_id="owner-1", aisle_id="aisle-1"
    )

    assert result.outcome == JobClaimOutcome.ACQUIRED
    assert result.may_execute is True
    assert client.last_txn is not None
    assert client.last_txn.commits == 1
    assert client.last_txn.rollbacks == 0
    sqls = [s for s, _ in client.last_txn.connection.cursor_obj.executions]
    assert any("UPDATE inventory_jobs" in s and "claim_owner_id" in s for s in sqls)
    assert any("AND status = ?" in s for s in sqls)
    cas_params = [
        p for s, p in client.last_txn.connection.cursor_obj.executions if "UPDATE inventory_jobs" in s
    ][0]
    assert "owner-1" in cas_params
    assert JobStatus.STARTING.value in cas_params


def test_try_claim_rolls_back_when_aisle_update_rowcount_zero() -> None:
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
    script = [
        {"rows": [SimpleNamespace(target_type="aisle", target_id="aisle-1", status="starting")]},
        {"rows": [SimpleNamespace(status="queued")]},
        {"rowcount": 1},
        {"rowcount": 0},
    ]
    client = _ClaimClient(script)
    repo = SqlJobRepository(client)  # type: ignore[arg-type]
    repo.get_by_id = MagicMock(return_value=_make_job())  # type: ignore[method-assign]

    result = repo.try_claim_starting_to_running(
        "job-1", now=now, claim_owner_id="owner-1", aisle_id="aisle-1"
    )

    assert result.outcome == JobClaimOutcome.TARGET_INVALID_STATUS
    assert client.last_txn is not None
    assert client.last_txn.commits == 0
    assert client.last_txn.rollbacks >= 1


def test_try_claim_target_mismatch_rolls_back_without_cas() -> None:
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
    script = [
        {"rows": [SimpleNamespace(target_type="aisle", target_id="aisle-other", status="starting")]},
    ]
    client = _ClaimClient(script)
    repo = SqlJobRepository(client)  # type: ignore[arg-type]

    result = repo.try_claim_starting_to_running(
        "job-1", now=now, claim_owner_id="owner-1", aisle_id="aisle-1"
    )

    assert result.outcome == JobClaimOutcome.TARGET_MISMATCH
    assert client.last_txn is not None
    assert client.last_txn.commits == 0
    assert client.last_txn.rollbacks >= 1
    assert not any(
        "UPDATE inventory_jobs" in s for s, _ in client.last_txn.connection.cursor_obj.executions
    )


def test_try_claim_exception_after_job_update_rolls_back() -> None:
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
    script = [
        {"rows": [SimpleNamespace(target_type="aisle", target_id="aisle-1", status="starting")]},
        {"rows": [SimpleNamespace(status="queued")]},
        {"rowcount": 1},
        {"raise": RuntimeError("aisle boom")},
    ]
    client = _ClaimClient(script)
    repo = SqlJobRepository(client)  # type: ignore[arg-type]

    try:
        repo.try_claim_starting_to_running(
            "job-1", now=now, claim_owner_id="owner-1", aisle_id="aisle-1"
        )
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass

    assert client.last_txn is not None
    assert client.last_txn.commits == 0
    assert client.last_txn.rollbacks >= 1


def test_try_reclaim_stale_updates_finalization_fields_and_commits() -> None:
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
    script = [
        {"rowcount": 1},
        {
            "rows": [
                SimpleNamespace(
                    target_type="aisle",
                    target_id="aisle-1",
                    claim_owner_id="owner-a",
                    attempt_count=2,
                )
            ]
        },
        {"rowcount": 1},
    ]
    client = _ClaimClient(script)
    repo = SqlJobRepository(client)  # type: ignore[arg-type]
    failed = _make_job()
    failed.status = JobStatus.FAILED
    failed.failure_code = STALE_FAILURE_CODE
    repo.get_by_id = MagicMock(return_value=failed)  # type: ignore[method-assign]

    result = repo.try_reclaim_stale_job_and_reconcile_aisle(
        "job-1", now=now, stale_after_seconds=60
    )

    assert result.won is True
    assert result.aisle_transition_applied is True
    assert client.last_txn is not None
    assert client.last_txn.commits == 1
    job_sql = client.last_txn.connection.cursor_obj.executions[0][0]
    assert "failure_code" in job_sql
    assert "finalization_status" in job_sql
    assert "finalization_error_code" in job_sql
    assert "finalization_started_at" in job_sql


def _job_row_ns(job: Job) -> SimpleNamespace:
    return SimpleNamespace(id=job.id)


def test_renew_lease_sql_includes_owner_token_and_expiry() -> None:
    from src.domain.jobs.lease import JobLease, LeaseRenewalOutcome

    now = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
    lease = JobLease(
        job_id="job-1",
        owner_id="owner-a",
        fencing_token=3,
        acquired_at=now,
        expires_at=now + __import__("datetime").timedelta(seconds=60),
    )
    client = RecordingClient(rowcounts=[1])
    repo = SqlJobRepository(client)  # type: ignore[arg-type]
    result = repo.renew_lease(lease, now=now, extension_seconds=60)
    assert result.outcome == LeaseRenewalOutcome.RENEWED
    sql, params = client.cursor_instance.executions[0]
    assert "lease_fencing_token = ?" in sql
    assert "claim_owner_id = ?" in sql
    assert "lease_expires_at >= ?" in sql
    assert "OUTPUT" not in sql  # renewal must not bump fencing token
    assert "owner-a" in params
    assert 3 in params


def test_complete_if_leased_sql_cas_where() -> None:
    from src.domain.jobs.lease import JobLease, LeaseWriteOutcome

    now = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
    lease = JobLease(
        job_id="job-1",
        owner_id="owner-a",
        fencing_token=2,
        acquired_at=now,
        expires_at=now + __import__("datetime").timedelta(seconds=60),
    )
    job = _make_job()
    job.id = "job-1"
    job.status = JobStatus.SUCCEEDED
    job.result_json = {"ok": True}
    client = RecordingClient(rowcounts=[1])
    repo = SqlJobRepository(client)  # type: ignore[arg-type]
    outcome = repo.complete_if_leased(lease, job, now=now)
    assert outcome.outcome == LeaseWriteOutcome.APPLIED
    sql, params = client.cursor_instance.executions[0]
    assert "status = ?" in sql
    assert "claim_owner_id = ?" in sql
    assert "lease_fencing_token = ?" in sql
    assert "lease_expires_at >= ?" in sql
    assert params[params.index("owner-a")] == "owner-a"
