"""Unit tests: SQL repos apply correct job_id predicates (Phase 1), without a live database."""

from __future__ import annotations

from src.infrastructure.repositories.sql_final_count_repository import SqlFinalCountRepository
from src.infrastructure.repositories.sql_normalized_label_repository import SqlNormalizedLabelRepository
from src.application.ports.repositories import JOB_ID_FILTER_UNSET
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_raw_label_repository import SqlRawLabelRepository


class RecordingCursor:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple]] = []
        self.rowcount = 0

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executions.append((sql, params))

    def fetchall(self) -> list:
        return []


class RecordingClient:
    def __init__(self) -> None:
        self.cursor_instance = RecordingCursor()

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance


def test_sql_raw_label_list_for_scope_null_job_uses_is_null() -> None:
    client = RecordingClient()
    repo = SqlRawLabelRepository(client)  # type: ignore[arg-type]
    list(repo.list_for_scope("inv-1", "aisle-1", job_id=None))
    sql, params = client.cursor_instance.executions[0]
    assert "job_id IS NULL" in sql
    assert params == ("inv-1", "aisle-1")


def test_sql_raw_label_list_for_scope_uuid_param() -> None:
    client = RecordingClient()
    repo = SqlRawLabelRepository(client)  # type: ignore[arg-type]
    list(repo.list_for_scope("inv-1", "aisle-1", job_id="job-a"))
    sql, params = client.cursor_instance.executions[0]
    assert "job_id = ?" in sql
    assert params == ("inv-1", "aisle-1", "job-a")


def test_sql_raw_label_list_for_scope_all_no_job_predicate() -> None:
    client = RecordingClient()
    repo = SqlRawLabelRepository(client)  # type: ignore[arg-type]
    list(repo.list_for_scope("inv-1", "aisle-1", job_id="all"))
    sql, params = client.cursor_instance.executions[0]
    assert "job_id" not in sql.split("WHERE")[1].split("ORDER BY")[0]
    assert params == ("inv-1", "aisle-1")


def test_sql_normalized_replace_for_scope_null_job() -> None:
    client = RecordingClient()
    repo = SqlNormalizedLabelRepository(client)  # type: ignore[arg-type]
    repo.replace_for_scope("inv-1", "aisle-1", job_id=None)
    sql, params = client.cursor_instance.executions[0]
    assert "DELETE FROM normalized_labels" in sql
    assert "job_id IS NULL" in sql
    assert params == ("inv-1", "aisle-1")


def test_sql_final_count_replace_for_scope_uuid() -> None:
    client = RecordingClient()
    repo = SqlFinalCountRepository(client)  # type: ignore[arg-type]
    repo.replace_for_scope("inv-1", "aisle-1", job_id="j1")
    sql, params = client.cursor_instance.executions[0]
    assert "DELETE FROM final_count_records" in sql
    assert "job_id = ?" in sql
    assert params == ("inv-1", "aisle-1", "j1")


def test_sql_position_list_by_aisle_legacy_and_job_scoped() -> None:
    client = RecordingClient()
    repo = SqlPositionRepository(client)  # type: ignore[arg-type]
    list(
        repo.list_by_aisle(
            "aisle-1",
            page=1,
            page_size=10,
            job_id=None,
        )
    )
    sql_null, params_null = client.cursor_instance.executions[0]
    assert "p.job_id IS NULL" in sql_null
    assert "aisle-1" in params_null

    list(
        repo.list_by_aisle(
            "aisle-1",
            page=1,
            page_size=10,
            job_id="job-x",
        )
    )
    sql_job, params_job = client.cursor_instance.executions[1]
    assert "p.job_id = ?" in sql_job
    assert "job-x" in params_job

    list(repo.list_by_aisle("aisle-1", page=1, page_size=10, job_id=JOB_ID_FILTER_UNSET))
    sql_all, params_all = client.cursor_instance.executions[2]
    assert "p.job_id" not in sql_all.split("WHERE")[1].split("ORDER BY")[0]
    assert params_all[0] == "aisle-1"
